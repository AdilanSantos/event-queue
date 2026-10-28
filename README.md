# Event Ingestion API

A FastAPI service that receives webhook events and guarantees they are
neither lost nor processed twice.

> 🇧🇷 [Leia em português](README.pt-BR.md)

## Status

🚧 In development. Core flow (ingestion, idempotency, queueing, worker with
retries, dead-letter queue) is implemented and covered by integration tests.

## Problem

Webhook senders retry when they don't get a timely response, so the same event
can arrive more than once. Queues give at-least-once delivery, which also means
copies. And if processing fails after the API has already answered `200`, the
sender won't retry and the event is lost.

This service addresses both:

- **Duplicates:** each event has a unique id from the sender, stored with a
  primary key. A repeated event is acknowledged without being processed again.
- **Loss:** the event is persisted before the API responds. Processing failures
  are recorded and retried by the worker, and events that exhaust their retries
  are kept in a dead-letter queue for investigation.

## Architecture

```
Sender ──POST /webhook──▶ API ──insert (idempotent)──▶ PostgreSQL
                            │
                            └──publish id──▶ RabbitMQ: events.incoming
                                                  │
                                                  ▼
                                               Worker
                                  claim (pending → processing)
                                                  │
                          ┌───────────────────────┴──────────────┐
                          ▼                                      ▼
                  processed (success)           retry with backoff (30s, 60s)
                                                        │ after 3 attempts
                                                        ▼
                                          failed + RabbitMQ: events.dead_letter
```

Key decisions:

- **Idempotency in the database.** A `PRIMARY KEY` on the sender's `id` lets
  `INSERT ... ON CONFLICT DO NOTHING` decide duplicates atomically, so no
  race condition depends on application code.
- **Duplicates return `202` with `status: "duplicate"`.** An error status would
  make senders retry and never stop.
- **Only new events are published.** `RETURNING` tells the API whether the row
  was inserted.
- **The message carries only the id.** The database is the source of truth; the
  worker reads the payload from it.
- **Claim with conditional `UPDATE`.** A worker only processes an event if it
  changes its status from `pending` (due) or a stale `processing` to
  `processing`. Two workers cannot claim the same event.
- **The database schedules retries.** A polling loop picks up `pending` events
  whose `next_attempt_at` has passed. The same loop covers events that never
  reached the queue.
- **Dead-letter by state.** After 3 attempts the event is marked `failed` with
  its last error, and its id is published to `events.dead_letter`.

## Tech stack

- Python 3.11+
- FastAPI and Pydantic v2
- SQLAlchemy 2.0 and psycopg2
- PostgreSQL 16
- RabbitMQ 3 (with management UI)
- pika
- pytest and httpx
- Docker Compose

## Project structure

```
src/
├── api/          # FastAPI routes and request/response schemas
├── core/         # configuration
├── db/           # engine, session, ORM model
├── services/     # claim, retry, publishing, processing
└── workers/      # RabbitMQ consumer and polling loop
docs/
└── schema.sql    # database schema, applied on first container start
tests/
└── integration/  # API, claim, retry and webhook tests
```

## Running locally

### 1. Start PostgreSQL and RabbitMQ

Requires Docker Desktop.

```bash
cp .env.example .env
docker compose up -d
```

The `schema.sql` file runs automatically the first time the PostgreSQL volume
is created.

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows (cmd): .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set environment variables

The API and the worker both read these from the environment (the `.env` file
is used by Docker Compose, not by Python):

```bash
export DATABASE_URL=postgresql+psycopg2://events:change_me@localhost:5432/events_db
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

On Windows `cmd`, use `set NAME=value` instead of `export`.

### 4. Start the services

Use three terminals, each with the variables above:

```bash
# Terminal 1: API
uvicorn src.main:app --reload

# Terminal 2: worker
python -m src.workers.event_consumer
```

Send an event at `http://localhost:8000/docs` (`POST /webhook`):

```json
{
  "id": "evt_001",
  "type": "payment.received",
  "occurred_at": "2026-10-27T10:00:00Z",
  "data": {"amount": 100}
}
```

Expected response: `202` with `{"id": "evt_001", "status": "accepted"}`.
Sending the same body again returns `"status": "duplicate"`.

Check the result:

- **Database:** `docker compose exec postgres psql -U events -d events_db -c "SELECT id, status, attempts FROM events;"`
- **RabbitMQ:** `http://localhost:15672` (user and password `guest`), queues
  `events.incoming` and `events.dead_letter`.

## Running tests

```bash
pytest -v
```

The test suite uses a separate database, `events_test`. It is dropped and
recreated from `docs/schema.sql` at the start of every run, so it never touches
development data.

## Known limitations

- Schema changes only apply to new volumes. Existing databases need a manual
  `ALTER TABLE` (or `docker compose down -v` in development).
- The processing step is a stub that only logs the event.
- The RabbitMQ publish opens a new connection per message. Production would
  reuse a connection and use publisher confirms.
- Duplicate ids are not checked against the payload: a sender reusing an id for
  a different body gets `duplicate`.
- Webhook signature validation (HMAC) is not implemented yet.
- The polling loop and the consumer share a process with no supervision.

## Roadmap

- HMAC signature validation on `POST /webhook`
- Reconciliation job for events published to nowhere (publish failed after commit)
- Real processing logic
- Deployment (Render or Railway) with managed PostgreSQL and RabbitMQ

## License

MIT