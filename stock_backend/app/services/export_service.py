"""用户数据导出服务（G17 · P1-5a 数据复制权）。

生成全量个人数据 ZIP：
- user.json          账号信息
- watchlist.json     关注列表
- support_resistance.json  支撑/压力位
- strategies/*.json + strategies/code/*.py   交易策略（元数据 + 代码文件）
- backtest.json      回测任务与结果
- conversations.json 会话与消息
- agents.json        定制 Agent 配置 + 运行记录 + 节点步骤
- memory/facts.json  记忆事实（PG）
- memory/files/*.md  原始记忆文件（人类可读）

文件存 EXPORT_DIR，默认 24h 后由 beat 清理任务删除；下载走签名 token。
"""

import json
import logging
import shutil
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent import AgentRun, AgentStep, MemoryChunk, UserAgent
from app.models.strategy import BacktestResult, BacktestTask, ChatMessage, Conversation, TradingStrategy
from app.models.user import SupportResistance, User, UserWatchlist
from app.repositories import export_repo

logger = logging.getLogger(__name__)
_settings = get_settings()


def export_dir() -> Path:
    """导出目录（不存在则创建）。"""
    path = Path(_settings.EXPORT_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_default(obj):
    """JSON 序列化兜底：datetime/Decimal → 字符串/浮点。"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=_json_default)


def _rows_to_dicts(rows, fields: list[str]) -> list[dict]:
    return [{f: getattr(r, f, None) for f in fields} for r in rows]


# ---------- 各数据域收集 ----------

def _collect_user(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "email_verified": user.email_verified,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _collect_watchlist(db: Session, user_id: int) -> list[dict]:
    rows = db.query(UserWatchlist).filter(UserWatchlist.user_id == user_id).all()
    return _rows_to_dicts(
        rows, ["id", "symbol_id", "sync_status", "last_synced_at", "created_at"]
    )


def _collect_support_resistance(db: Session, user_id: int) -> list[dict]:
    rows = db.query(SupportResistance).filter(SupportResistance.user_id == user_id).all()
    return _rows_to_dicts(rows, ["id", "symbol_id", "type", "price", "note", "created_at"])


def _collect_strategies(db: Session, user_id: int) -> list[dict]:
    rows = db.query(TradingStrategy).filter(TradingStrategy.user_id == user_id).all()
    return _rows_to_dicts(
        rows, ["id", "title", "description", "code", "params", "status", "created_at", "updated_at"]
    )


def _collect_backtest(db: Session, user_id: int) -> dict:
    """回测任务与结果（经 strategy_id 归属用户）。"""
    strategy_ids = [s.id for s in db.query(TradingStrategy.id).filter(TradingStrategy.user_id == user_id)]
    if not strategy_ids:
        return {"tasks": [], "results": []}
    tasks = db.query(BacktestTask).filter(BacktestTask.strategy_id.in_(strategy_ids)).all()
    results = db.query(BacktestResult).filter(BacktestResult.strategy_id.in_(strategy_ids)).all()
    return {
        "tasks": _rows_to_dicts(
            tasks,
            ["id", "strategy_id", "symbol_id", "period", "start_ts", "end_ts", "fill_on",
             "status", "progress", "error", "created_at", "updated_at"],
        ),
        "results": _rows_to_dicts(
            results,
            ["id", "task_id", "strategy_id", "symbol_id", "win_rate", "profit_loss_ratio", "sharpe",
             "total_buys", "total_sells", "annual_return", "max_drawdown", "metrics_json",
             "start_ts", "end_ts", "created_at"],
        ),
    }


def _collect_conversations(db: Session, user_id: int) -> list[dict]:
    """会话与消息（消息按会话聚合，避免大表全量笛卡尔积）。"""
    convs = db.query(Conversation).filter(Conversation.user_id == user_id).all()
    out: list[dict] = []
    for c in convs:
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == c.id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
            .all()
        )
        out.append(
            {
                "id": c.id,
                "title": c.title,
                "summary": c.summary,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "messages": _rows_to_dicts(
                    msgs, ["id", "role", "symbol_id", "content", "tokens", "created_at"]
                ),
            }
        )
    return out


def _collect_agents(db: Session, user_id: int) -> dict:
    agents = db.query(UserAgent).filter(UserAgent.user_id == user_id).all()
    runs = db.query(AgentRun).filter(AgentRun.user_id == user_id).all()
    run_ids = [r.id for r in runs]
    steps = db.query(AgentStep).filter(AgentStep.run_id.in_(run_ids)).all() if run_ids else []
    return {
        "agents": _rows_to_dicts(
            agents,
            ["id", "name", "agent_type", "system_prompt", "tools", "llm_config",
             "memory_config", "status", "created_at", "updated_at"],
        ),
        "runs": _rows_to_dicts(
            runs,
            ["id", "agent_id", "conversation_id", "symbol_id", "run_type", "status",
             "input", "output", "tokens", "duration_ms", "error", "created_at", "updated_at"],
        ),
        "steps": _rows_to_dicts(
            steps,
            ["id", "run_id", "step_name", "agent_role", "content", "summary",
             "duration_ms", "status", "meta", "created_at"],
        ),
    }


def _collect_memory_facts(db: Session, user_id: int) -> list[dict]:
    rows = db.query(MemoryChunk).filter(MemoryChunk.user_id == user_id).all()
    return _rows_to_dicts(
        rows, ["id", "source_type", "source_id", "content", "importance", "file_path", "created_at"]
    )


# ---------- 打包 ----------

def build_export_zip(db: Session, task_id: int) -> Path:
    """生成导出 ZIP，返回文件路径。调用方（Celery 任务）负责更新任务状态。"""
    task = export_repo.get(db, task_id)
    if task is None:
        raise ValueError(f"导出任务不存在: {task_id}")
    user = db.get(User, task.user_id)
    if user is None:
        raise ValueError(f"用户不存在: {task.user_id}")

    export_repo.update_status(db, task, "running", progress=5)
    db.commit()

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"export_user{user.id}_{task_id}_{ts}.zip"
    zip_path = export_dir() / filename
    tmp_dir = export_dir() / f".tmp_{task_id}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1) 各数据域落盘为 JSON 文件
        (tmp_dir / "user.json").write_text(_dump(_collect_user(db, user)), encoding="utf-8")
        export_repo.update_status(db, task, "running", progress=15)
        db.commit()

        (tmp_dir / "watchlist.json").write_text(_dump(_collect_watchlist(db, user.id)), encoding="utf-8")
        (tmp_dir / "support_resistance.json").write_text(
            _dump(_collect_support_resistance(db, user.id)), encoding="utf-8"
        )

        # 2) 策略：元数据 JSON + 代码独立 .py 文件
        strategies = _collect_strategies(db, user.id)
        (tmp_dir / "strategies").mkdir(exist_ok=True)
        (tmp_dir / "strategies" / "strategies.json").write_text(_dump(strategies), encoding="utf-8")
        code_dir = tmp_dir / "strategies" / "code"
        code_dir.mkdir(exist_ok=True)
        for s in strategies:
            if s.get("code"):
                (code_dir / f"strategy_{s['id']}.py").write_text(s["code"], encoding="utf-8")
        export_repo.update_status(db, task, "running", progress=35)
        db.commit()

        (tmp_dir / "backtest.json").write_text(_dump(_collect_backtest(db, user.id)), encoding="utf-8")
        export_repo.update_status(db, task, "running", progress=50)
        db.commit()

        (tmp_dir / "conversations.json").write_text(
            _dump(_collect_conversations(db, user.id)), encoding="utf-8"
        )
        export_repo.update_status(db, task, "running", progress=70)
        db.commit()

        (tmp_dir / "agents.json").write_text(_dump(_collect_agents(db, user.id)), encoding="utf-8")

        # 3) 记忆：事实 JSON + 原始 md 文件
        (tmp_dir / "memory").mkdir(exist_ok=True)
        (tmp_dir / "memory" / "facts.json").write_text(
            _dump(_collect_memory_facts(db, user.id)), encoding="utf-8"
        )
        user_memory_dir = Path(_settings.MEMORY_DIR) / str(user.id)
        if user_memory_dir.exists():
            shutil.copytree(user_memory_dir, tmp_dir / "memory" / "files", dirs_exist_ok=True)

        export_repo.update_status(db, task, "running", progress=85)
        db.commit()

        # 4) 打包为 ZIP
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tmp_dir.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(tmp_dir).as_posix())

        size = zip_path.stat().st_size
        expires_at = datetime.now(UTC) + timedelta(hours=_settings.EXPORT_TTL_HOURS)
        export_repo.update_status(
            db, task, "success", progress=100, file_path=str(zip_path), file_size=size
        )
        task.expires_at = expires_at
        db.commit()
        logger.info("export task %s done: %s (%s bytes)", task_id, zip_path.name, size)
        return zip_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def delete_export_file(file_path: str | None) -> bool:
    """删除导出文件（幂等）。返回是否实际删除。"""
    if not file_path:
        return False
    p = Path(file_path)
    try:
        if p.exists():
            p.unlink()
            return True
    except OSError:
        logger.warning("delete export file failed: %s", file_path, exc_info=True)
    return False


def cleanup_expired_exports(db: Session) -> int:
    """清理过期导出：删文件 + 置 expired。返回处理条数。"""
    rows = export_repo.list_expired(db)
    for row in rows:
        delete_export_file(row.file_path)
        export_repo.update_status(db, row, "expired")
        row.file_path = None  # 文件已删除，清空路径避免误导
    if rows:
        db.commit()
    return len(rows)
