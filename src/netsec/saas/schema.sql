CREATE TABLE IF NOT EXISTS subscriptions (
 org_id TEXT PRIMARY KEY REFERENCES organizations(id), plan TEXT NOT NULL,
 status TEXT NOT NULL, trial_end TEXT NOT NULL, period_end TEXT NOT NULL,
 provider TEXT NOT NULL DEFAULT 'local', customer_id TEXT UNIQUE, subscription_id TEXT UNIQUE,
 cancel_at_end INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_months (
 org_id TEXT NOT NULL REFERENCES organizations(id), month TEXT NOT NULL,
 events INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(org_id,month)
);
CREATE TABLE IF NOT EXISTS action_tokens (
 token_hash TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 purpose TEXT NOT NULL, email TEXT NOT NULL, user_id TEXT, payload TEXT NOT NULL,
 expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verified_users (
 user_id TEXT PRIMARY KEY REFERENCES users(id), verified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mail_jobs (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), recipient TEXT NOT NULL,
 encrypted_body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_at TEXT NOT NULL, lease_until TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tenant_integrations (
 org_id TEXT PRIMARY KEY REFERENCES organizations(id), encrypted_config TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_requests (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), plan TEXT NOT NULL,
 provider_id TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_events (
 event_id TEXT PRIMARY KEY, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS incident_tasks (
 incident_id TEXT PRIMARY KEY REFERENCES incidents(id) ON DELETE CASCADE,
 org_id TEXT NOT NULL REFERENCES organizations(id), due_at TEXT NOT NULL,
 next_reminder TEXT NOT NULL, reminders INTEGER NOT NULL DEFAULT 0, ticket_ref TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS service_alerts (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 alert_key TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(org_id,alert_key)
);
CREATE TABLE IF NOT EXISTS privacy_requests (
 id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), user_id TEXT NOT NULL,
 kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS oidc_transactions (
 state_hash TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id),
 browser_hash TEXT NOT NULL, encrypted_params TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oidc_bindings (
 org_id TEXT NOT NULL REFERENCES organizations(id), issuer TEXT NOT NULL, subject TEXT NOT NULL,
 user_id TEXT NOT NULL REFERENCES users(id), PRIMARY KEY(org_id,issuer,subject)
);
CREATE TABLE IF NOT EXISTS worker_heartbeats (
 id TEXT PRIMARY KEY, updated_at TEXT NOT NULL
);
