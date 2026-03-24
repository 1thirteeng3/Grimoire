DROP INDEX IF EXISTS idx_pact_audit_session;
DROP INDEX IF EXISTS idx_pact_audit_pact;
DROP INDEX IF EXISTS idx_pacts_session;
DROP INDEX IF EXISTS idx_pacts_ttl;

DROP TABLE IF EXISTS pact_audit_events;
DROP TABLE IF EXISTS routing_events;
DROP TABLE IF EXISTS session_summaries;
DROP TABLE IF EXISTS pending_pacts;
