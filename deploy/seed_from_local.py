# -*- coding: utf-8 -*-
"""开发栈种子数据引导：把本机原生 PostgreSQL 的数据导入 Docker 开发库（stock-invest-dev-db-1）。

背景：Docker 开发栈 db 是独立空卷，api 启动只建表 + 种 49 个固定指数 symbol，
没有用户/K线/快照/重点关注等数据，导致页面打开空白、账号登录不上。本脚本在
`docker compose up` 且 api 完成迁移后，把本机库（127.0.0.1:5432/stock_invest）数据
搬运到容器库，使容器环境延续本地开发数据、打开即有数据。

设计：
- 宿主运行（用 stock_backend/.venv 的 psycopg2 读本机 PG18），经 `docker exec -i db psql`
  写入容器 PG16，绕开 pg_dump 18→16 版本不兼容；
- 以容器库迁移后的表为准（自动发现 public 普通表/分区子表，排除分区父表与 alembic_version）；
- 幂等：容器库 users 已有数据则跳过（--force 可强制重建）；
- 本机库未运行/连不上时优雅跳过（退出码 0，不阻断 start-dev.bat 启动）。

用法：
    python deploy/seed_from_local.py            # 空库才引导
    python deploy/seed_from_local.py --force    # 强制以本机库覆盖容器库
"""

import io
import subprocess
import sys
import time

import psycopg2

# ---- 配置（可用环境变量覆盖）----
LOCAL_DSN = dict(host="127.0.0.1", port=5432, dbname="stock_invest",
                 user="postgres", password="123456", connect_timeout=5)
DB_CONTAINER = "stock-invest-dev-db-1"
# 导入期间需暂停的后台容器（worker/beat 会持续写 task_logs/sync_tasks，与 TRUNCATE+COPY 竞争主键）
PAUSE_CONTAINERS = ["stock-invest-dev-worker-1", "stock-invest-dev-beat-1"]
PSQL = ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "postgres", "-d", "stock_invest"]
EXCLUDE_TABLES = {"alembic_version"}
WAIT_TIMEOUT = 120  # 等待容器迁移完成的最长秒数


def docker_ctrl(action: str, containers: list[str]) -> None:
    """docker start/stop 指定容器（失败仅告警，不阻断）。"""
    if not containers:
        return
    p = subprocess.run(["docker", action, *containers], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print(f"[seed] docker {action} {containers} 告警: {p.stderr.strip()}")
    else:
        print(f"[seed] docker {action}: {', '.join(containers)}")


def psql_scalar(sql: str) -> str | None:
    """在容器库执行查询，返回单值（-t -A 去格式）。"""
    p = subprocess.run(PSQL + ["-t", "-A", "-c", sql], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"psql 查询失败: {p.stderr.strip()}")
    v = p.stdout.strip()
    return v or None


def psql_exec(sql: str) -> None:
    """在容器库执行无结果 SQL。"""
    p = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"psql 执行失败 [{sql[:60]}]: {p.stderr.strip()}")


def psql_copy_into(table: str, csv_bytes: bytes) -> None:
    """把 CSV 字节流经 stdin COPY 进容器库指定表（session 内禁用外键触发器，顺序无关）。"""
    cmd = PSQL + [
        "-c", "SET session_replication_role = replica",
        "-c", f'COPY "{table}" FROM STDIN WITH (FORMAT csv)',
    ]
    p = subprocess.run(cmd, input=csv_bytes, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"COPY 进表 {table} 失败: {p.stderr.decode('utf-8', 'replace').strip()}")


# 导入带显式主键的数据后，把所有自增序列对齐到各列 max 值；否则序列停在初始值，后续 INSERT 撞主键
RESET_SEQUENCES_SQL = r"""
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT c.relname AS tablename, a.attname AS colname,
           pg_get_serial_sequence(c.relname, a.attname) AS seq
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
    WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
      AND pg_get_serial_sequence(c.relname, a.attname) IS NOT NULL
  LOOP
    EXECUTE format(
      'SELECT setval(%L, COALESCE((SELECT max(%I) FROM %I), 1), (SELECT max(%I) FROM %I) IS NOT NULL)',
      r.seq, r.colname, r.tablename, r.colname, r.tablename);
  END LOOP;
END $$;
"""


def reset_sequences() -> None:
    """对齐容器库所有自增序列到当前列最大值（COPY 显式 id 后必需）。"""
    psql_exec(RESET_SEQUENCES_SQL)


def wait_container_ready() -> bool:
    """等待容器 db 可用且迁移到 head（alembic_version=0008）。"""
    deadline = time.time() + WAIT_TIMEOUT
    while time.time() < deadline:
        try:
            ver = psql_scalar("SELECT version_num FROM alembic_version")
            if ver:
                print(f"[seed] 容器库迁移完成，alembic={ver}")
                return True
        except Exception:
            pass
        print("[seed] 等待容器 db 与迁移完成 ...")
        time.sleep(3)
    return False


def container_tables() -> list[str]:
    """容器库 public 下普通表 + 分区子表（relkind='r'），排除分区父表('p')与黑名单。"""
    sql = (
        "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind='r' ORDER BY relname"
    )
    p = subprocess.run(PSQL + ["-t", "-A", "-c", sql], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return [t for t in p.stdout.split() if t not in EXCLUDE_TABLES]


def main() -> int:
    force = "--force" in sys.argv

    # 1) 本机库是否可用（不可用则优雅跳过，不阻断启动）
    try:
        local = psycopg2.connect(**LOCAL_DSN)
    except Exception as e:  # noqa: BLE001
        print(f"[seed] 未连接到本机原生库(127.0.0.1:5432/stock_invest)，跳过种子引导：{str(e)[:80]}")
        return 0

    # 2) 等容器迁移就绪
    if not wait_container_ready():
        print("[seed] 等待容器迁移超时，跳过种子引导（可稍后手动重跑本脚本）")
        local.close()
        return 0

    # 3) 幂等：容器已有用户数据则跳过
    existing = int(psql_scalar("SELECT count(*) FROM users") or 0)
    if existing > 0 and not force:
        print(f"[seed] 容器库已有 {existing} 个用户，种子数据已存在，跳过（--force 可覆盖）")
        local.close()
        return 0

    # 4) 以容器库表为准，取本地存在数据的交集表
    target_tables = container_tables()
    lcur = local.cursor()
    lcur.execute("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                 "WHERE n.nspname='public' AND c.relkind='r'")
    local_tables = {r[0] for r in lcur.fetchall()}
    todo = [t for t in target_tables if t in local_tables]
    skipped = [t for t in target_tables if t not in local_tables]
    if skipped:
        print(f"[seed] 本机库无此表，跳过: {skipped}")

    # 5) 清空容器目标表（CASCADE + 重置序列），随后逐表 COPY；
    #    先暂停 worker/beat，避免其在 TRUNCATE 后抢先写入导致 COPY 主键冲突
    docker_ctrl("stop", PAUSE_CONTAINERS)
    try:
        trunc = "TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in todo) + " RESTART IDENTITY CASCADE"
        psql_exec(trunc)

        ok = 0
        for t in todo:
            buf = io.BytesIO()
            lcur.copy_expert(f'COPY "{t}" TO STDOUT WITH (FORMAT csv)', buf)
            data = buf.getvalue()
            psql_copy_into(t, data)
            rows = data.count(b"\n") if data else 0
            print(f"[seed] 导入 {t:28s} {rows:>6d} 行")
            ok += 1

        # 关键：COPY 带显式主键后对齐所有自增序列，避免 worker/api 后续 INSERT 撞主键
        reset_sequences()
        print("[seed] 已对齐所有自增序列到 max(id)")
    finally:
        # 无论成功失败都恢复后台容器
        docker_ctrl("start", PAUSE_CONTAINERS)

    lcur.close()
    local.close()
    print(f"[seed] 完成，共引导 {ok} 张表。容器库用户数="
          f"{psql_scalar('SELECT count(*) FROM users')}, 标的数={psql_scalar('SELECT count(*) FROM symbols')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
