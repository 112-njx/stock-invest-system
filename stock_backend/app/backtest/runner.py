"""策略子进程隔离执行（G08 · P1-4a）。

问题
----
策略代码此前在 Celery worker **主进程**内执行：死循环只能靠 Celery 硬超时
（``BACKTEST_HARD_TIME_LIMIT``）杀 worker 兜底 —— 代价是 worker 进程被终止重启，
在途的其它任务全部丢失；且没有 CPU/内存上限，恶意策略可以直接把 worker 撑爆。

方案
----
每次回测在**独立子进程**内跑引擎，父进程（worker）只做调度与 DB 写入：

- 子进程设 ``RLIMIT_CPU`` / ``RLIMIT_AS``（**仅 POSIX**，见下方平台差异）；
- 父进程墙钟超时后 ``terminate()`` → 必要时 ``kill()``，worker 主进程与其它任务不受影响；
- 进度经管道回传，**DB 写入全部发生在父进程**（子进程不碰数据库，保持事务语义）。

平台差异（重要，不要假装两端一致）
----------------------------------
============  =============================  ==========================
项目          Linux（生产容器）             Windows（本地开发）
============  =============================  ==========================
启动方式      ``forkserver``                 ``spawn``（无 ``resource`` 模块）
CPU 上限      ``RLIMIT_CPU`` 生效           ❌ 不生效
内存上限      ``RLIMIT_AS`` 生效            ❌ 不生效
死循环防护    ✅ 父进程 terminate            ✅ 父进程 terminate
============  =============================  ==========================

启动方式刻意**不用 fork**：Celery worker 是多线程进程，``fork`` 出的子进程可能继承其它线程
在 fork 瞬间持有的锁而死锁（Python 3.12 起发 ``DeprecationWarning``，3.14 在 Linux 已默认改
forkserver）。forkserver 从一个干净的单线程服务进程 fork，代价是 bars 需 pickle
（8k 根约 30ms，相对回测耗时可忽略）。确需 fork 的性能可用
``BACKTEST_SUBPROCESS_START_METHOD=fork`` 显式开启（自担死锁风险）。

即：**死循环防护两端都有**（靠 terminate），只有 CPU/内存**硬上限**是 POSIX 专属。
测试按平台分别断言，不含糊。

RLIMIT_AS 的坑（必须这样设）
---------------------------
worker 进程 import 了 chromadb / onnxruntime 等重依赖，``fork`` 后子进程**继承**父进程的
地址空间映射（VSZ 可能已 1GB+）。若直接把 ``RLIMIT_AS`` 设成 512MB，子进程**任何新分配都会
立即失败**（当前用量已超限额），策略连第一行都跑不起来。因此这里读子进程当前 VSZ，
把限额设为 ``当前 VSZ + 配置预算`` —— 语义是「**策略自身额外增长**不超过 N MB」，
自校准、与基线大小无关。
"""

import logging
import multiprocessing
import os
import signal
import time
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings

from .engine import BacktestConfig, BacktestEngine, BacktestError

_settings = get_settings()

logger = logging.getLogger(__name__)

# 子进程收到结果后，父进程等待其自行退出的时间；超时再 terminate
_GRACEFUL_EXIT_SECONDS = 5.0
# 父进程轮询管道/子进程状态的间隔
_POLL_INTERVAL = 0.2

_SIGXCPU = getattr(signal, "SIGXCPU", None)  # Windows 无此信号
_SIGKILL = getattr(signal, "SIGKILL", None)


class StrategyResourceError(BacktestError):
    """策略超出资源限制（墙钟超时 / CPU / 内存）——不可重试。

    继承 ``BacktestError`` 以便 ``backtest_service`` 统一按业务错误处理（不重试）：
    让一个死循环或吃内存的策略重试只会再死一次。
    """


# --------------------------------------------------------------------------- #
# 子进程侧：资源限制
# --------------------------------------------------------------------------- #
def _current_vsz_bytes() -> int:
    """当前进程虚拟内存大小（Linux 读 /proc/self/statm）。"""
    try:
        with open("/proc/self/statm") as fh:
            pages = int(fh.read().split()[0])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError, AttributeError):
        return 0


def _apply_limits(cpu_seconds: int, memory_bytes: int) -> dict:
    """在子进程内施加 rlimit。返回实际生效的限额（供父进程记录/监控）。"""
    try:
        import resource
    except ImportError:  # Windows：无 rlimit，只剩父进程 terminate 兜底
        return {"enforced": False, "reason": "resource module unavailable (Windows)"}

    info: dict[str, Any] = {"enforced": True}
    if cpu_seconds > 0:
        # 软限制触发 SIGXCPU；硬限制再宽 5s，避免来不及清理
        resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_seconds), int(cpu_seconds) + 5))
        info["cpu_seconds"] = int(cpu_seconds)
    if memory_bytes > 0:
        baseline = _current_vsz_bytes()
        limit = baseline + memory_bytes
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            info["memory_bytes"] = int(memory_bytes)
            info["baseline_vsz_bytes"] = baseline
        except (ValueError, OSError) as e:  # 限额低于当前用量等
            info["memory_error"] = f"{type(e).__name__}: {e}"
    return info


def _child_main(conn, payload: dict) -> None:
    """子进程入口：施加限额 → 跑引擎 → 把结果/错误送回父进程。"""
    limits = _apply_limits(payload.get("cpu_seconds", 0), payload.get("memory_bytes", 0))

    # fork 会继承父进程的 SQLAlchemy 连接池。子进程不做任何 DB 操作，
    # 这里 dispose(close=False) 让池里的连接对象不被子进程退出时误关父进程的 socket。
    try:
        from app.utils.db import engine

        engine.dispose(close=False)
    except Exception:  # noqa: BLE001 —— 清理失败不应影响策略执行
        pass

    def _progress(pct: int) -> None:
        try:
            conn.send({"type": "progress", "pct": pct})
        except (BrokenPipeError, OSError, ValueError):
            pass  # 父进程已放弃（超时），进度丢掉即可

    try:
        config = BacktestConfig(**payload["config"])
        out = BacktestEngine(config).run(
            payload["code"], payload["params"], payload["bars"], progress_cb=_progress
        )
        conn.send({"type": "done", "result": out, "limits": limits})
    except Exception as e:  # noqa: BLE001 —— 含 MemoryError；统一回报给父进程判定
        try:
            conn.send({"type": "error", "error": f"{type(e).__name__}: {e}", "limits": limits})
        except Exception:  # noqa: BLE001 —— 内存超限时连序列化都可能失败
            pass
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# 父进程侧：进程编排
# --------------------------------------------------------------------------- #
def _exit_reason(exitcode: int | None) -> str:
    """把子进程退出码翻译成人能看懂的原因。"""
    if exitcode is None:
        return "策略子进程未正常结束"
    if exitcode < 0:
        signum = -exitcode
        if _SIGXCPU is not None and signum == _SIGXCPU:
            return "策略 CPU 时间超出上限，子进程已被终止（疑似死循环或超重计算）"
        if _SIGKILL is not None and signum == _SIGKILL:
            return "策略子进程被强制终止（通常为内存超限被 OOM killer 回收）"
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = f"signal {signum}"
        return f"策略子进程被信号终止（{name}）"
    return f"策略子进程异常退出（exitcode={exitcode}）"


def _shutdown(proc: multiprocessing.process.BaseProcess, *, immediate: bool) -> int | None:
    """收敛子进程：优雅等待 → terminate → kill。返回退出码。"""
    if immediate:
        proc.terminate()
    else:
        proc.join(timeout=_GRACEFUL_EXIT_SECONDS)
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=_GRACEFUL_EXIT_SECONDS)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=_GRACEFUL_EXIT_SECONDS)
    return proc.exitcode


def start_method() -> str:
    """实际使用的子进程启动方式。

    ``auto`` 在 POSIX 上取 **forkserver**（不是 fork）—— Celery worker 是多线程进程，
    ``fork`` 出的子进程可能继承其它线程在 fork 瞬间持有的锁而死锁；Python 3.12 起会发
    ``DeprecationWarning``，3.14 在 Linux 上已把默认改为 forkserver。forkserver 从一个
    干净的单线程服务进程 fork，代价是 bars 需 pickle（8k 根约 30ms，相对回测耗时可忽略）。
    """
    configured = (_settings.BACKTEST_SUBPROCESS_START_METHOD or "auto").strip().lower()
    if configured and configured != "auto":
        return configured
    return "forkserver" if os.name == "posix" else "spawn"


def run_isolated(
    code: str,
    params: dict | None,
    bars: list[dict],
    config: BacktestConfig,
    *,
    grace: float = 15.0,
    cpu_seconds: int = 0,
    memory_bytes: int = 0,
    on_progress: Callable[[int], None] | None = None,
) -> dict:
    """在独立子进程中执行回测，返回引擎输出（额外带 ``_subprocess`` 运行信息）。

    墙钟上限 = ``config.time_budget + grace``，应显著小于 Celery 软超时，
    以保证是**策略失败**而不是 **worker 被杀**。

    失败语义：策略自身异常 → ``BacktestError``；超时/资源超限 → ``StrategyResourceError``。
    两者都不可重试。
    """
    ctx = multiprocessing.get_context(start_method())
    recv_conn, send_conn = ctx.Pipe(duplex=False)
    payload = {
        "code": code,
        "params": params or {},
        "bars": bars,
        "config": {
            "initial_cash": config.initial_cash,
            "commission_rate": config.commission_rate,
            "stamp_duty_rate": config.stamp_duty_rate,
            "fill_on": config.fill_on,
            "slippage_pct": config.slippage_pct,
            "time_budget": config.time_budget,
            "period": config.period,
            "max_volume_pct": config.max_volume_pct,
        },
        "cpu_seconds": cpu_seconds,
        "memory_bytes": memory_bytes,
    }
    proc = ctx.Process(target=_child_main, args=(send_conn, payload), daemon=True, name="backtest-strategy")
    deadline = time.monotonic() + config.time_budget + grace
    started = time.monotonic()
    proc.start()
    # 父进程必须关掉写端，否则子进程退出后 recv 端等不到 EOF（会一直阻塞）
    send_conn.close()

    message: dict | None = None
    timed_out = False
    try:
        while True:
            if recv_conn.poll(_POLL_INTERVAL):
                try:
                    msg = recv_conn.recv()
                except EOFError:
                    break  # 未发结果就断开（被信号杀 / 崩溃）
                if msg.get("type") == "progress":
                    if on_progress is not None:
                        on_progress(int(msg.get("pct", 0)))
                    continue
                message = msg
                break
            if not proc.is_alive():
                if recv_conn.poll(_GRACEFUL_EXIT_SECONDS):
                    continue  # 进程已退出但管道还有数据，读完再走
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
    finally:
        exitcode = _shutdown(proc, immediate=timed_out)
        recv_conn.close()

    elapsed = round(time.monotonic() - started, 2)
    if message is not None and message.get("type") == "done":
        result = message["result"]
        result["_subprocess"] = {
            "pid": proc.pid,
            "exitcode": exitcode,
            "elapsed_s": elapsed,
            "limits": message.get("limits"),
        }
        return result
    if message is not None and message.get("type") == "error":
        # 策略自身错误（含 MemoryError）→ BacktestError，与进程内执行行为一致
        raise BacktestError(f"策略执行失败: {message.get('error')}")
    if timed_out:
        raise StrategyResourceError(
            f"策略执行超过墙钟上限 {config.time_budget + grace:.0f}s，子进程已被强制终止（疑似死循环）"
        )
    raise StrategyResourceError(_exit_reason(exitcode))


def limits_effective() -> bool:
    """当前平台是否真正施加 rlimit（POSIX）。供测试与文档判断，勿用于业务分支。"""
    try:
        import resource  # noqa: F401
    except ImportError:
        return False
    return True
