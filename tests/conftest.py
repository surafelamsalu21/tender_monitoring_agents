"""Pytest fixtures: isolated SQLite DB + FastAPI TestClient."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(monkeypatch, tmp_path):
    import app.core.database as db_module

    db_file = tmp_path / "auth_api_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)

    import app.models  # noqa: F401 — register models on Base.metadata

    db_module.Base.metadata.create_all(bind=engine)

    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        yield tc
