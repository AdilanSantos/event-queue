from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from src.services.event_service import claim_event, PROCESSING_TIMEOUT
from tests.conftest import TestingSessionLocal


def insert_event(**fields):
    defaults = {
        "id": "evt_claim",
        "status": "pending",
        "attempts": 0,
        "payload": "{}",
        "next_attempt_at": None,
        "processing_started_at": None,
    }
    defaults.update(fields)
    with TestingSessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO events (id, status, attempts, payload, next_attempt_at, processing_started_at)
                VALUES (:id, :status, :attempts, CAST(:payload AS jsonb), :next_attempt_at, :processing_started_at)
            """),
            defaults,
        )
        db.commit()


def test_claims_pending_event():
    insert_event()
    with TestingSessionLocal() as db:
        assert claim_event(db, "evt_claim") is True


def test_second_claim_fails_when_already_processing():
    insert_event()
    with TestingSessionLocal() as db:
        assert claim_event(db, "evt_claim") is True
        assert claim_event(db, "evt_claim") is False


def test_does_not_claim_retry_scheduled_in_future():
    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    insert_event(next_attempt_at=future)
    with TestingSessionLocal() as db:
        assert claim_event(db, "evt_claim") is False


def test_reclaims_stale_processing_event():
    stale = datetime.now(timezone.utc) - PROCESSING_TIMEOUT - timedelta(minutes=1)
    insert_event(status="processing", processing_started_at=stale, attempts=1)
    with TestingSessionLocal() as db:
        assert claim_event(db, "evt_claim") is True