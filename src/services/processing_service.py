import logging

logger = logging.getLogger(__name__)


def process_event(event_id: str, payload: dict) -> None:
    """registra o evento."""
    raise RuntimeError("falha simulada")
    logger.info("Processando evento %s do tipo %s", event_id, payload.get("type"))