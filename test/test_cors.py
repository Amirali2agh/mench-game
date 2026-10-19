"""CORS allowlist tests (issue #8).

The API has no cookie session, so the browser only needs CORS when the frontend
is served from a different origin than the API. The defaults must therefore be
"no CORS at all", the allowlist must be exact, and the old
``allow_origins=["*"] + allow_credentials=True`` combination must be impossible
outside debug mode.
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import configure_cors


def _client(origins: list[str]) -> TestClient:
    api = FastAPI()

    @api.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    configure_cors(api, origins)
    return TestClient(api)


def test_empty_allowlist_installs_no_cors_middleware():
    api = FastAPI()
    configure_cors(api, [])

    assert all(middleware.cls is not CORSMiddleware for middleware in api.user_middleware)


def test_allowed_origin_is_echoed_without_credentials():
    client = _client(["http://localhost:3000"])

    response = client.get("/ping", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in response.headers


def test_disallowed_origin_gets_no_cors_headers():
    client = _client(["http://localhost:3000"])

    response = client.get("/ping", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_allows_only_get_and_post():
    client = _client(["http://localhost:3000"])
    origin = {"Origin": "http://localhost:3000"}

    allowed = client.options(
        "/ping",
        headers={**origin, "Access-Control-Request-Method": "POST"},
    )
    rejected = client.options(
        "/ping",
        headers={**origin, "Access-Control-Request-Method": "DELETE"},
    )

    assert allowed.status_code == 200
    assert "POST" in allowed.headers["access-control-allow-methods"]
    assert "*" not in allowed.headers["access-control-allow-methods"]
    # Starlette rejects a disallowed method with 400 and never lists it.
    assert rejected.status_code == 400
    assert "DELETE" not in rejected.headers["access-control-allow-methods"]


def test_preflight_rejects_unknown_headers():
    client = _client(["http://localhost:3000"])

    response = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Not-Allowed",
        },
    )

    assert response.status_code == 400
    assert response.text == "Disallowed CORS headers"


def test_allowlist_is_normalised():
    settings = Settings(ALLOWED_CORS_ORIGINS=" http://a.example/ , http://b.example ,")

    assert settings.cors_origins == ["http://a.example", "http://b.example"]


def test_wildcard_is_allowed_in_debug_mode():
    settings = Settings(DEBUG=True, ALLOWED_CORS_ORIGINS="*")

    assert settings.cors_origins == ["*"]


def test_wildcard_is_rejected_outside_debug_mode():
    with pytest.raises(ValidationError) as error:
        Settings(DEBUG=False, ALLOWED_CORS_ORIGINS="*")

    assert "only allowed when DEBUG=true" in str(error.value)
