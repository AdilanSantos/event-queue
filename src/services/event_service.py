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