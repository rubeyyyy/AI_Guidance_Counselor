from tests.test_students import client  # noqa: F401


def test_development_cors_preflight(client):
    response = client.options('/students', headers={
        'Origin': 'http://127.0.0.1:5173',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'
    assert 'access-control-allow-credentials' not in response.headers


def test_unknown_origin_is_not_allowed(client):
    response = client.options('/students', headers={
        'Origin': 'https://untrusted.example',
        'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers
