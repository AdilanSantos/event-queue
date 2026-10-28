from sqlalchemy import text

from tests.conftest import test_engine


def payload(event_id="evt_test_001"):
    return {
        "id": event_id,
        "type": "payment.received",
        "occurred_at": "2026-10-27T10:00:00Z",
        "data": {"amount": 100},
    }


def count_events(event_id):
    with test_engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM events WHERE id = :id"), {"id": event_id}
        ).scalar()


def test_valid_event_is_accepted_and_stored(client):
    response = client.post("/webhook", json=payload())

    assert response.status_code == 202
    assert response.json() == {"id": "evt_test_001", "status": "accepted"}
    assert count_events("evt_test_001") == 1


def test_duplicate_event_returns_success_without_new_row(client):
    client.post("/webhook", json=payload())
    response = client.post("/webhook", json=payload())

    assert response.status_code == 202
    assert count_events("evt_test_001") == 1


def test_empty_id_is_rejected(client):
    response = client.post("/webhook", json=payload(event_id=""))
    assert response.status_code == 422


def test_id_longer_than_64_chars_is_rejected(client):
    response = client.post("/webhook", json=payload(event_id="x" * 65))
    assert response.status_code == 422


def test_invalid_date_is_rejected(client):
    body = payload()
    body["occurred_at"] = "ontem"
    response = client.post("/webhook", json=body)
    assert response.status_code == 422

def test_duplicate_returns_duplicate_status(client):
    client.post("/webhook", json=payload())
    response = client.post("/webhook", json=payload())

    assert response.status_code == 202
    assert response.json()["status"] == "duplicate"