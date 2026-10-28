from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

PROCESSING_TIMEOUT = timedelta(minutes=5)


def claim_event(db: Session, event_id: str) -> bool:
    """
    Tenta assumir o evento para processamento.

    Retorna True se este worker ganhou o evento, False se outro worker já o
    pegou, se ele já foi finalizado, ou se ainda não está na hora do retry.
    """
    now = datetime.now(timezone.utc)
    stale_before = now - PROCESSING_TIMEOUT

    result = db.execute(
        text("""
            UPDATE events
            SET status = 'processing',
                processing_started_at = :now,
                attempts = attempts + 1
            WHERE id = :id
              AND (
                    (status = 'pending' AND (next_attempt_at IS NULL OR next_attempt_at <= :now))
                 OR (status = 'processing' AND processing_started_at <= :stale_before)
              )
            RETURNING id
        """),
        {"id": event_id, "now": now, "stale_before": stale_before},
    )
    claimed = result.scalar_one_or_none() is not None
    db.commit()
    return claimed


RETRY_DELAYS = [timedelta(seconds=30), timedelta(seconds=60)]
MAX_ATTEMPTS = 3


def mark_processed(db: Session, event_id: str) -> None:
    db.execute(
        text("""
            UPDATE events
            SET status = 'processed', last_attempt_at = now()
            WHERE id = :id
        """),
        {"id": event_id},
    )
    db.commit()


def mark_retry_or_failed(db: Session, event_id: str, error: str) -> None:
    attempts = db.execute(
        text("SELECT attempts FROM events WHERE id = :id"), {"id": event_id}
    ).scalar_one()

    if attempts < 1:
        raise ValueError(f"attempts inválido para {event_id}: {attempts}")

    if attempts >= MAX_ATTEMPTS:
        db.execute(
            text("""
                UPDATE events
                SET status = 'failed',
                    last_attempt_at = now(),
                    next_attempt_at = NULL,
                    last_error = :error
                WHERE id = :id
            """),
            {"id": event_id, "error": error},
        )
    else:
        delay = RETRY_DELAYS[attempts - 1]
        db.execute(
            text("""
                UPDATE events
                SET status = 'pending',
                    last_attempt_at = now(),
                    next_attempt_at = now() + :delay,
                    last_error = :error
                WHERE id = :id
            """),
            {"id": event_id, "delay": delay, "error": error},
        )
    db.commit()