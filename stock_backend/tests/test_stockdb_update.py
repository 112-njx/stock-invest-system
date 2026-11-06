from types import SimpleNamespace
from unittest.mock import Mock
import time
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_current_admin
from app.services import stockdb_update as update
from app.services.stockdb_files import read_json, write_json


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setattr(update, 'directory', lambda: tmp_path)
    write_json(tmp_path / 'heartbeat.json', {'time': time.time()})
    db = Mock()
    db.scalar.return_value = None
    monkeypatch.setattr(update, 'get_session', lambda: db)
    return tmp_path, db


def test_update_requires_live_helper_and_rejects_running_sync(control):
    root, db = control
    db.scalar.return_value = SimpleNamespace(status='running')
    with pytest.raises(HTTPException) as error:
        update.request_update()
    assert error.value.status_code == 409
    assert not (root / 'request.json').exists()
    write_json(root / 'heartbeat.json', {'time': 0})
    with pytest.raises(HTTPException) as error:
        update.request_update()
    assert error.value.status_code == 503


def test_update_publishes_only_fixed_job_and_blocks_duplicate(control):
    root, _ = control
    state = update.request_update()
    job = read_json(root / 'request.json')
    assert job['operation'] == 'update'
    assert job['task_id'] == state['task_id']
    assert state['maintenance']
    with pytest.raises(HTTPException) as error:
        update.request_update()
    assert error.value.status_code == 409


def test_retry_requires_updater_exit(control):
    root, _ = control
    write_json(root / 'status.json', {'status': 'failed'})
    write_json(root / 'maintenance.json', {})
    write_json(root / 'updater-process.json', {'pid': 123})
    with pytest.raises(HTTPException):
        update.request_update()
    (root / 'updater-process.json').unlink()
    assert update.request_update()['status'] == 'queued'


def test_update_routes_require_admin(control):
    with TestClient(app) as client:
        assert client.get('/api/v1/admin/local-market/update').status_code == 401
        assert client.post('/api/v1/admin/local-market/update').status_code == 401
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(id=1)
    try:
        with TestClient(app) as client:
            assert client.get('/api/v1/admin/local-market/update').json()['data']['helper_online']
            result = client.post('/api/v1/admin/local-market/update')
            assert result.status_code == 200
            assert result.json()['data']['status'] == 'queued'
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


@pytest.mark.parametrize('recovery_write_fails', [False, True])
def test_queue_write_failure_is_retryable_without_orphan_files(control, monkeypatch, recovery_write_fails):
    root, _ = control

    def fail_submission(path, value):
        if path.name == 'request.json':
            # Include cleanup of any residual published request.
            write_json(path, value)
            raise OSError('simulated queue write failure')
        if recovery_write_fails and value.get('status') == 'failed':
            raise OSError('simulated full disk during recovery')
        write_json(path, value)

    monkeypatch.setattr(update, 'write_json', fail_submission)
    with pytest.raises(OSError, match='queue write failure'):
        update.request_update()
    state = update.status()
    assert state['status'] == ('idle' if recovery_write_fails else 'failed')
    assert not state['maintenance']
    assert not (root / 'request.json').exists()
    if not recovery_write_fails:
        assert state['can_retry']
        assert 'queue write failure' in state['error']

    monkeypatch.setattr(update, 'write_json', write_json)
    retried = update.request_update()
    assert retried['status'] == 'queued'
    assert read_json(root / 'request.json')['task_id'] == retried['task_id']
