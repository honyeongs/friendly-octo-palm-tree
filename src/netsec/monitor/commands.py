"""Operator CLI; passwords are read interactively, never in process arguments."""

import getpass
import json
from pathlib import Path


def add_commands(commands, port_type):
    monitor = commands.add_parser("monitor", help="Run persistent login security monitoring")
    monitor.add_argument("--host", default="127.0.0.1")
    monitor.add_argument("--port", type=port_type, default=8890)
    monitor.add_argument("--env-file", type=Path)
    admin = commands.add_parser("monitor-admin", help="Provision organizations, back up or prune data")
    admin.add_argument("--env-file", type=Path)
    actions = admin.add_subparsers(dest="action", required=True)
    org = actions.add_parser("create-org")
    org.add_argument("--name", required=True)
    org.add_argument("--email", required=True)
    org.add_argument("--display-name", default="Administrator")
    restore = actions.add_parser("backup")
    restore.add_argument("destination", type=Path)
    actions.add_parser("prune")
    reset = actions.add_parser("reset-password")
    reset.add_argument("--org-id", required=True)
    reset.add_argument("--email", required=True)
    sample = commands.add_parser("demo-app", help="Run a local application that emits real login events")
    sample.add_argument("--port", type=port_type, default=8891)
    sample.add_argument("--endpoint", default="http://127.0.0.1:8890")
    agent = commands.add_parser("agent", help="Send OpenSSH or journal exports with a durable cursor")
    agent.add_argument("input", type=Path)
    agent.add_argument("--format", choices=("auto", "openssh", "journal"), default="auto")
    agent.add_argument("--endpoint", default="http://127.0.0.1:8890")
    agent.add_argument("--outbox", type=Path, default=Path("data/agent-outbox.sqlite3"))
    agent.add_argument("--follow", action="store_true")
    agent.add_argument("--interval", type=int, default=5, choices=range(1, 3601), metavar="SECONDS")


def run(args):
    if args.env_file:
        from dotenv import load_dotenv
        if not args.env_file.is_file():
            raise ValueError("Environment file does not exist")
        load_dotenv(args.env_file, override=False)
    from netsec.monitor.config import Settings
    settings = Settings.from_env()
    if args.command == "monitor":
        if args.host not in ("127.0.0.1", "localhost", "::1") and not settings.secure:
            raise ValueError("External bind requires HTTPS NETSEC_ORIGIN and a trusted TLS reverse proxy")
        import uvicorn
        from netsec.monitor.app import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=False, access_log=False)
    else:
        from netsec.monitor.database import Database
        db = Database(settings.database)
        if args.action == "create-org":
            from netsec.monitor.accounts import create_organization
            from netsec.monitor.schemas import Setup
            first = getpass.getpass("Admin password (12+ characters): ")
            if not 12 <= len(first) <= 256 or first != getpass.getpass("Confirm password: "):
                raise ValueError("Password length or confirmation is invalid")
            setup = Setup(organization=args.name, email=args.email, display_name=args.display_name, password=first)
            with db.connect(write=True) as conn:
                org_id = create_organization(conn, setup)
            print("Organization ID: " + org_id)
        elif args.action == "reset-password":
            from netsec.monitor.database import audit
            from netsec.monitor.security import hash_password
            first = getpass.getpass("New password (12+ characters): ")
            if len(first) < 12 or len(first) > 256 or first != getpass.getpass("Confirm password: "):
                raise ValueError("Password length or confirmation is invalid")
            with db.connect(write=True) as conn:
                user = conn.execute("SELECT id FROM users WHERE org_id=? AND email=?", (args.org_id, args.email.lower())).fetchone()
                if user is None:
                    raise ValueError("User not found")
                conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(first), user["id"]))
                conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
                audit(conn, args.org_id, "operator", "password.reset", user["id"])
            print("Password reset; existing sessions revoked")
        elif args.action == "backup":
            from netsec.monitor.maintenance import backup
            print(backup(db, args.destination))
        else:
            from netsec.monitor.maintenance import prune
            print(json.dumps(prune(db, settings.retention_days)))
    return 0
