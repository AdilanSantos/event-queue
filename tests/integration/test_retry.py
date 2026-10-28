from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from src.services.event_service import mark_retry_or_failed
from tests.conftest import TestingSessionLocal


def insert_event(event_id: str, attempts: int) -> None:
    with TestingSessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO events (id, status, attempts, payload, processing_started_at)
                VALUES (:id, 'processing', :attempts, '{}'::jsonb, now())
            """),
            {"id": event_id, "attempts": attempts},
        )
        db.commit()


def read_event(event_id: str):
    with TestingSessionLocal() as db:
        return db.execute(
            text("""
                SELECT status, attempts, last_error, next_attempt_at, now() AS db_now
                FROM events WHERE id = :id
            """),
            {"id": event_id},
        ).one()


def test_first_failure_schedules_retry_in_30_seconds():
    insert_event("evt_retry_1", attempts=1)
    with TestingSessionLocal() as db:
        became_failed = mark_retry_or_failed(db, "evt_retry_1", "boom")

    row = read_event("evt_retry_1")
    assert became_failed is False
    assert row.status == "pending"
    assert row.last_error == "boom"
    delay = row.next_attempt_at - row.db_now
    assert timedelta(seconds=29) <= delay <= timedelta(seconds=31)


def test_second_failure_schedules_retry_in_60_seconds():
    insert_event("evt_retry_2", attempts=2)
    with TestingSessionLocal() as db:
        became_failed = mark_retry_or_failed(db, "evt_retry_2", "boom")

    row = read_event("evt_retry_2")
    assert became_failed is False
    assert row.status == "pending"
    delay = row.next_attempt_at - row.db_now
    assert timedelta(seconds=59) <= delay <= timedelta(seconds=61)


def test_third_failure_marks_failed_and_returns_true():
    insert_event("evt_retry_3", attempts=3)
    with TestingSessionLocal() as db:
        became_failed = mark_retry_or_failed(db, "evt_retry_3", "boom")

    row = read_event("evt_retry_3")
    assert became_failed is True
    assert row.status == "failed"
    assert row.next_attempt_at is None
    assert row.last_error == "boom"


def test_zero_attempts_raises_value_error():
    insert_event("evt_retry_0", attempts=0)
    with TestingSessionLocal() as db:
        with pytest.raises(ValueError):
            mark_retry_or_failed(db, "evt_retry_0", "boom")