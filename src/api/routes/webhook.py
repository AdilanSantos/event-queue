from fastapi import APIRouter, Depends, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.schemas import EventAccepted, EventIn
from src.db.database import get_db
from src.db.models import Event

router = APIRouter()


@router.post(
    "/webhook",
    response_model=EventAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def receive_webhook(event_in: EventIn, db: Session = Depends(get_db)):
    # ON CONFLICT DO NOTHING: se o id já existe, o banco ignora o insert
    # sem erro. Essa é a garantia de idempotência feita pelo banco.
    stmt = (
        insert(Event)
        .values(
            id=event_in.id,
            payload={"type": event_in.type, "occurred_at": event_in.occurred_at.isoformat(), "data": event_in.data},
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    db.execute(stmt)
    db.commit()

    return EventAccepted(id=event_in.id, status="accepted")