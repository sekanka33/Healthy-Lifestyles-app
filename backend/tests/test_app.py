from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_health():
    res = TestClient(app).get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_unknown_route_uses_standard_error_shape():
    res = TestClient(app).get("/nope")
    assert res.status_code == 404
    assert set(res.json()["error"]) >= {"code", "message"}


def test_production_refuses_insecure_defaults():
    s = Settings(environment="production", jwt_secret="dev-insecure-change-me", token_encryption_key=None, _env_file=None)
    try:
        s.validate_production()
    except RuntimeError as e:
        assert "JWT_SECRET" in str(e) and "TOKEN_ENCRYPTION_KEY" in str(e)
    else:
        raise AssertionError("insecure production config was accepted")
