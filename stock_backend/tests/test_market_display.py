from types import SimpleNamespace
from app.api.deps import get_current_admin
from app.main import app
from app.services import market_display, market_policy
import pytest


def test_display_setting_requires_admin(client):
    assert client.get('/api/v1/admin/market-display').status_code == 401
    assert client.put('/api/v1/admin/market-display', json={'synthetic_wick_factor': 0}).status_code == 401


def test_display_setting_is_public_and_independent_of_source_flags(client):
    original = market_display.read()
    policy = market_policy.read()
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(is_admin=True)
    try:
        for factor in (0, 0.25, 0.5, 1):
            response = client.put('/api/v1/admin/market-display', json={'synthetic_wick_factor': factor})
            assert response.status_code == 200
            assert response.json()['data']['synthetic_wick_factor'] == factor
            assert client.get('/api/v1/market/display-settings').json()['data']['synthetic_wick_factor'] == factor
        assert market_policy.read() == policy
    finally:
        market_display.save(original['synthetic_wick_factor'])
        app.dependency_overrides.pop(get_current_admin)


@pytest.mark.parametrize('value', [-1, 1.01, 'NaN', 'Infinity', None])
def test_display_setting_rejects_invalid_coefficients(client, value):
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(is_admin=True)
    try:
        assert client.put('/api/v1/admin/market-display', json={'synthetic_wick_factor': value}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_admin)
