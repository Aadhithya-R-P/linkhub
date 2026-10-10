from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.routes import redirects


def test_unavailable_page_and_api_errors_stay_separate(monkeypatch):
    def unused_db():
        yield None

    monkeypatch.setattr(redirects, "get_redirect_destination", lambda session, code: None)
    app.dependency_overrides[get_db] = unused_db
    try:
        with TestClient(app) as client:
            response = client.get('/r/private-example', follow_redirects=False)
            assert response.status_code == 404
            assert response.headers['content-type'].startswith('text/html')
            assert response.headers['cache-control'] == 'no-store'
            assert 'location' not in response.headers
            assert '<h1>This link is unavailable</h1>' in response.text
            assert 'href="https://linkhub-five-theta.vercel.app/"' in response.text
            assert 'Go to LinkHub' in response.text
            assert 'private-example' not in response.text
            api_response = client.get('/api/does-not-exist')
            assert api_response.status_code == 404
            assert api_response.headers['content-type'].startswith('application/json')
            assert api_response.json() == {'detail': 'Not Found'}
    finally:
        app.dependency_overrides.pop(get_db, None)
