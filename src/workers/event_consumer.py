import logging
import os
import time

import pika
from sqlalchemy import text

from src.db.database import SessionLocal
from src.services.event_service import claim_event, mark_processed, mark_retry_or_failed
from src.services.processing_service import process_event

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
QUEUE_NAME = "events.incoming"
POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 20


def handle_event(event_id: str) -> None:
    """Assume o evento, processa e registra o resultado."""
    with SessionLocal() as db:
        if not claim_event(db, event_id):
            return

        payload_row = db.execute(
            text("SELECT payload FROM events WHERE id = :id"), {"id": event_id}
        ).scalar_one()

        try:
            process_event(event_id, payload_row)
        except Exception as exc:
            logger.exception("Falha ao processar %s", event_id)
            mark_retry_or_failed(db, event_id, str(exc))
        else:
            mark_processed(db, event_id)


def poll_due_events() -> None:
    """Busca eventos pendentes vencidos, cobrindo retries e eventos sem publish."""
    with SessionLocal() as db:
        ids = db.execute(
            text("""
                SELECT id FROM events
                WHERE status = 'pending'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                ORDER BY received_at
                LIMIT :limit
            """),
            {"limit": BATCH_SIZE},
        ).scalars().all()

    for event_id in ids:
        handle_event(event_id)


def on_message(channel, method, properties, body: bytes) -> None:
    event_id = body.decode()
    try:
        handle_event(event_id)
    except Exception:
        logger.exception("Erro inesperado no evento %s", event_id)
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)


def main() -> None:
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    logger.info("Worker aguardando mensagens em %s", QUEUE_NAME)
    last_poll = 0.0

    while True:
        connection.process_data_events(time_limit=1)
        if time.monotonic() - last_poll >= POLL_INTERVAL_SECONDS:
            poll_due_events()
            last_poll = time.monotonic()


if __name__ == "__main__":
    main()