"""Account isolation, validation and custom MA API contracts."""
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.main import app
from app.api.deps import get_current_user
from app.models.user import User
from app.utils.db import get_session
from app.schemas.chart_settings import ChartSettings, MaParameters

@pytest.fixture
def accounts():
    with get_session() as db:
        users = [User(username='chart_' + uuid4().hex, password_hash='test-only') for _ in range(2)]
        db.add_all(users); db.commit()
        ids = [u.id for u in users]
    try:
        yield ids
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        with get_session() as db:
            db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False); db.commit()

def test_chart_settings_require_login(client):
    assert client.get('/api/v1/users/me/chart-settings').status_code == 401
    assert client.put('/api/v1/users/me/chart-settings', json={}).status_code == 401

def test_accounts_save_reload_and_isolation(client, accounts):
    active = [accounts[0]]
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=active[0])
    url = '/api/v1/users/me/chart-settings'
    default = client.get(url).json()['data']
    assert default == ChartSettings().model_dump()
    custom = {'ma': {'lines': [{'period': n, 'visible': n != 7} for n in [7,20,60,120,250,10000]]}, 'panels': ['volume','macd','kdj']}
    assert client.put(url, json=custom).json()['data'] == custom
    assert client.get(url).json()['data'] == custom
    active[0] = accounts[1]
    assert client.get(url).json()['data'] == default
    active[0] = accounts[0]
    custom['panels'] = []
    assert client.put(url, json=custom).json()['data']['panels'] == []
    assert client.put(url, json={**custom, 'panels': ['volume','amount','macd','kdj']}).status_code == 422
    assert client.get(url).json()['data']['panels'] == []

@pytest.mark.parametrize('periods', [[], [5,5], [0], [10001], [True], [1.5], list(range(1,8))])
def test_reject_invalid_ma_parameters(client, periods):
    result = client.get('/api/v1/indicators', params={'symbol': '300502', 'names': 'ma', 'params': json.dumps({'ma': {'periods': periods}})})
    assert result.status_code == 400

@pytest.mark.parametrize('lines', [[], [{'period':5},{'period':5}], [{'period':0}], [{'period':True}], [{'period':i} for i in range(1,8)]])
def test_preferences_validate_ma(lines):
    with pytest.raises(ValueError): ChartSettings.model_validate({'ma': {'lines': lines}})

def test_ma_parameter_default_compatibility():
    assert MaParameters().periods == [5,10,20,30]
