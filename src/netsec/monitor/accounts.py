"""Organization provisioning shared by first-run setup and operator CLI."""

from netsec.monitor.database import audit, identifier, now
from netsec.monitor.security import hash_password


def create_organization(conn, setup):
    org_id, user_id, stamp = identifier(), identifier(), now()
    conn.execute("INSERT INTO organizations(id,name,created_at) VALUES(?,?,?)", (org_id, setup.organization, stamp))
    conn.execute("INSERT INTO users(id,org_id,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,'admin',?)",
                 (user_id, org_id, setup.email, setup.display_name, hash_password(setup.password), stamp))
    audit(conn, org_id, user_id, "organization.create", org_id)
    return org_id
