PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS organizations (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
 threshold INTEGER NOT NULL DEFAULT 5, window_seconds INTEGER NOT NULL DEFAULT 60,
 success_seconds INTEGER NOT NULL DEFAULT 300, notification_email TEXT NOT NULL DEFAULT '',
 webhook_enabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 email TEXT NOT NULL, display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','analyst','viewer')), active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, UNIQUE(org_id,email)
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('app','ssh')),
 token_hash TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL REFERENCES organizations(id),
 source_id TEXT NOT NULL REFERENCES sources(id), event_id TEXT NOT NULL,
 timestamp TEXT NOT NULL, received_at TEXT NOT NULL, event_type TEXT NOT NULL,
 outcome TEXT NOT NULL, source_ip TEXT NOT NULL, username TEXT NOT NULL, method TEXT NOT NULL,
 host TEXT NOT NULL, fingerprint TEXT NOT NULL, UNIQUE(source_id,event_id)
);
CREATE INDEX IF NOT EXISTS events_scope_time ON events(org_id,source_id,timestamp);
CREATE TABLE IF NOT EXISTS incidents (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 source_id TEXT NOT NULL REFERENCES sources(id), rule TEXT NOT NULL,
 severity TEXT NOT NULL, source_ip TEXT NOT NULL, username TEXT NOT NULL,
 title TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', assignee_id TEXT REFERENCES users(id),
 evidence_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS incidents_scope_time ON incidents(org_id,last_seen);
CREATE TABLE IF NOT EXISTS comments (
 id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
 org_id TEXT NOT NULL REFERENCES organizations(id), author_id TEXT NOT NULL REFERENCES users(id),
 body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exclusions (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 source_id TEXT NOT NULL REFERENCES sources(id), cidr TEXT NOT NULL, reason TEXT NOT NULL,
 expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL REFERENCES organizations(id),
 actor_id TEXT NOT NULL, action TEXT NOT NULL, target_id TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_scope_time ON audit(org_id,created_at);
CREATE TABLE IF NOT EXISTS outbox (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
 channel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_at TEXT NOT NULL, lease_until TEXT, error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, UNIQUE(incident_id,channel)
);
CREATE TABLE IF NOT EXISTS rate_limits (
 key TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL
);
