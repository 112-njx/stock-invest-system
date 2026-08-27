import sys
from datetime import datetime, UTC
sys.path.insert(0, '.')
from app.core.config import get_settings
from sqlalchemy import create_engine, text

s = get_settings()
engine = create_engine(s.DATABASE_URL)
with engine.connect() as conn:
    now = datetime.now(UTC)
    print('当前UTC时间:', now)
    # 指数快照最新更新时间
    mx = conn.execute(text("SELECT MAX(updated_at) FROM snapshot_realtime WHERE symbol_id BETWEEN 70 AND 82")).fetchall()
    print('指数快照最新 updated_at:', mx)
    # 所有快照最新更新时间
    mx2 = conn.execute(text("SELECT MAX(updated_at) FROM snapshot_realtime")).fetchall()
    print('全部快照最新 updated_at:', mx2)
    # 赛力斯 watchlist 状态
    wl = conn.execute(text("SELECT w.symbol_id, w.sync_status, w.last_synced_at, w.created_at FROM user_watchlist w WHERE w.symbol_id=11825")).fetchall()
    print('赛力斯 watchlist:', wl)
