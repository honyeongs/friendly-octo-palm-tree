"""Select an input adapter without guessing missing years or time zones."""

from pathlib import Path

from netsec.models import ParseResult
from netsec.parsers import journal, ssh


def read_auth_log(path: Path, input_format: str = "auto") -> tuple[ParseResult, str]:
    if input_format not in {"auto", "openssh", "journal"}:
        raise ValueError("Unknown input format")
    with path.open(encoding="utf-8-sig") as stream:
        selected = input_format
        if selected == "auto":
            first = next((line.lstrip() for line in stream if line.strip()), "")
            selected = "journal" if first.startswith("{") else "openssh"
            stream.seek(0)
        adapter = journal if selected == "journal" else ssh
        return adapter.parse_lines(stream), selected
