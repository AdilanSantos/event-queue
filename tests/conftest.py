import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pathlib import Path



TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://events:change_me@localhost:5432/events_test",
)

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

from src.db.database import get_db  # noqa: E402
from src.main import app  # noqa: E402

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "schema.sql"
ADMIN_DATABASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database():
    """Recria o banco de teste e aplica o schema.sql antes da suíte."""
    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[1]

    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with test_engine.begin() as conn:
        conn.exec_driver_sql(schema_sql)

    yield
    test_engine.dispose()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_events_table():
    with test_engine.begin() as conn:
        conn.execute(text("TRUNCATE events"))
    yield