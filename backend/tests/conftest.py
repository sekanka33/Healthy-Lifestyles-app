import os

# Tests must never touch a real database, mail server or third-party API.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("EMAIL_PROVIDER", "disabled")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")

import re  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.db.session as session_module  # noqa: E402
import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.email import TEST_OUTBOX  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture
def db_factory(monkeypatch):
    # One shared in-memory connection so the app's threads and the test see the same data.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", factory)

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    TEST_OUTBOX.clear()
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(db_factory):
    return TestClient(app)


def last_code(to: str) -> str:
    msg = next(m for m in reversed(TEST_OUTBOX) if m.to == to)
    return re.search(r"\b(\d{6})\b", msg.text).group(1)


def register(client, email="ada@example.com", password=PASSWORD, timezone="Africa/Johannesburg", **extra):
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "first_name": "Ada", "timezone": timezone, **extra,
    })
    assert res.status_code == 201, res.text
    return res.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def verified(client):
    """A registered, verified user: returns (headers, session_json)."""
    s = register(client)
    h = auth(s["access_token"])
    res = client.post("/api/v1/auth/verify-email", json={"code": last_code("ada@example.com")}, headers=h)
    assert res.status_code == 200, res.text
    return h, s
