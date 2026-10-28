import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.schemas import EventAccepted, EventIn
from src.db.database import get_db
from src.db.models import Event
from src.services.rabbit_service import publish_event_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/webhook",
    response_model=EventAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def receive_webhook(event_in: EventIn, db: Session = Depends(get_db)):

    stmt = (
        insert(Event)
        .values(
            id=event_in.id,
            payload={
                "type": event_in.type,
                "occurred_at": event_in.occurred_at.isoformat(),
                "data": event_in.data,
            },
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Event.id)
    )
    inserted_id = db.execute(stmt).scalar_one_or_none()
    db.commit()

    status_msg = "accepted"

    if inserted_id is not None:
        try:
            publish_event_id(event_in.id)
        except Exception:
            logger.exception(
                "Falha ao publicar evento %s; será republicado pela reconciliação",
                event_in.id,
            )
    else:
        status_msg = "duplicate"

    return EventAccepted(id=event_in.id, status=status_msg)

