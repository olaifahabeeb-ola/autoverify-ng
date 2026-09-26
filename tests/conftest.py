"""
Shared pytest fixtures for the AutoVerify NG test suite.

Every test runs against an isolated, temporary SQLite database — never
the real autoverify.db — so tests never touch real data and can't
interfere with each other or with a running dev/production instance.

The database is reset (dropped + recreated + reseeded with demo data)
before every single test function, so each test starts from the exact
same known state: 2 demo officers (officer1/officer123, admin/admin123)
and 2 demo vehicles (ABC-123-XY, LND-456-KJ), matching README.md.
"""

import os
import sys
import tempfile

import pytest

# Point the app at a throwaway database BEFORE it's imported, since
# app.py reads SQLALCHEMY_DATABASE_URI at import time.
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["FLASK_DEBUG"] = "0"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as flask_app_module  # noqa: E402
from models import db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    yield
    with flask_app_module.app.app_context():
        db.session.remove()
        db.engine.dispose()
    os.close(_TEST_DB_FD)
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)


@pytest.fixture(autouse=True)
def reset_database():
    """Fresh, freshly-seeded schema before every test — full isolation."""
    with flask_app_module.app.app_context():
        db.drop_all()
        db.create_all()
        flask_app_module.seed_demo_data()
    yield


@pytest.fixture
def app():
    flask_app_module.app.config["TESTING"] = True
    return flask_app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def officer_client(app):
    """A test client already logged in as the demo field officer.
    Uses its own client instance (not the shared `client` fixture) so it
    never shares a session/cookie jar with officer_client/admin_client/
    owner_client used in the same test."""
    c = app.test_client()
    c.post("/officer/login", data={"username": "officer1", "password": "officer123"})
    return c


@pytest.fixture
def admin_client(app):
    """A test client already logged in as the demo admin (own client instance —
    see officer_client docstring)."""
    c = app.test_client()
    c.post("/officer/login", data={"username": "admin", "password": "admin123"})
    return c


@pytest.fixture
def owner_client(app):
    """A test client already logged in as the demo vehicle owner (own client
    instance — see officer_client docstring)."""
    c = app.test_client()
    c.post("/login", data={"email": "chinedu@example.com", "password": "password123"})
    return c
