"""Independent, persistent choice of indicator calculator."""
from sqlalchemy import text
from app.utils.db import get_session


def read():
    with get_session() as db:
        return dict(db.execute(text('SELECT pandas_enabled, revision FROM indicator_settings WHERE id=1')).mappings().one())


def save(enabled):
    with get_session() as db:
        db.execute(text('UPDATE indicator_settings SET pandas_enabled=:enabled, revision=revision+1 WHERE id=1'), {'enabled': enabled})
        db.commit()
    from app.ws.publisher import _publish
    _publish({'type': 'indicator_settings_changed'})
    return read()
