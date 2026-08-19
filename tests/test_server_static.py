"""Serving the built dashboard from the server: static files mounted behind the API."""

from fastapi.testclient import TestClient

from server.main import create_app


def _dist(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>GHL DASHBOARD SHELL</body></html>")
    return dist


def test_serves_web_dist_when_configured(server_settings, tmp_path):
    settings = server_settings(serve_web_dist=str(_dist(tmp_path)))
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "GHL DASHBOARD SHELL" in response.text


def test_api_routes_win_over_static(server_settings, tmp_path):
    settings = server_settings(serve_web_dist=str(_dist(tmp_path)))
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/proposals")

    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"proposals": []}
