
CREATE TABLE events (
    id                     VARCHAR(64)  PRIMARY KEY,
    received_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    status                 VARCHAR(20)  NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    attempts               INTEGER      NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    processing_started_at  TIMESTAMPTZ  NULL,
    last_attempt_at        TIMESTAMPTZ  NULL,
    next_attempt_at        TIMESTAMPTZ  NULL,
    payload                JSONB        NOT NULL,

    CONSTRAINT chk_final_has_attempt
        CHECK (status NOT IN ('processed', 'failed') OR last_attempt_at IS NOT NULL),
    CONSTRAINT chk_processing_has_start
        CHECK (status = 'pending' OR processing_started_at IS NOT NULL)
);

CREATE INDEX idx_events_next_attempt
    ON events (next_attempt_at)
    WHERE status IN ('pending', 'processing');