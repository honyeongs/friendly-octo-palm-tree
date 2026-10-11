from datetime import datetime, timedelta, timezone

from netsec.parsers.ssh import parse_lines


def log_line(
    seconds: float = 0, *, ip: str = "192.0.2.10", host: str = "lab",
    username: str = "alice", outcome: str = "Failed", method: str = "password",
    invalid: bool = False,
) -> str:
    timestamp = datetime(2026, 10, 11, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    user = ("invalid user " if invalid else "") + username
    return (f"{timestamp.isoformat()} {host} sshd[123]: {outcome} {method} "
            f"for {user} from {ip} port 50001 ssh2")


def events_at(seconds: list[float], **kwargs):
    return parse_lines(log_line(second, **kwargs) for second in seconds).events
