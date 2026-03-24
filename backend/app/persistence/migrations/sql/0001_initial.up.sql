CREATE TABLE IF NOT EXISTS pending_pacts (
    pact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    entity_manifest_hash TEXT NOT NULL,
    fsm_status TEXT NOT NULL DEFAULT 'PENDING_HUMAN_CONFLICT',
    operator_proposal_raw TEXT NOT NULL,
    tool_intent_json TEXT NOT NULL,
    critic_report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ttl_timestamp TEXT NOT NULL,
    cryptographic_signature TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_summaries (
    summary_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    domain TEXT
);

CREATE TABLE IF NOT EXISTS routing_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    feedback_score REAL NOT NULL,
    edit_delta REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pact_audit_events (
    event_id TEXT PRIMARY KEY,
    pact_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pacts_ttl ON pending_pacts(ttl_timestamp);
CREATE INDEX IF NOT EXISTS idx_pacts_session ON pending_pacts(session_id);
CREATE INDEX IF NOT EXISTS idx_pact_audit_pact ON pact_audit_events(pact_id);
CREATE INDEX IF NOT EXISTS idx_pact_audit_session ON pact_audit_events(session_id);
