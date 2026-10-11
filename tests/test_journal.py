import json
import unittest
from datetime import datetime, timezone

from netsec.parsers.journal import parse_line, parse_lines


def record(**changes):
    data = {"__REALTIME_TIMESTAMP": "1791676800123456", "_HOSTNAME": "lab",
            "SYSLOG_IDENTIFIER": "sshd", "MESSAGE": "Failed publickey for alice from 192.0.2.10 port 50001 ssh2: ED25519 SHA256:demo"}
    data.update(changes)
    return json.dumps(data)


class JournalTests(unittest.TestCase):
    def test_native_microseconds_preserved(self):
        event = parse_line(record(), 9)
        self.assertEqual(event.timestamp, datetime.fromtimestamp(1791676800, timezone.utc).replace(microsecond=123456))
        self.assertEqual(event.line_number, 9)
        self.assertEqual(event.method, "publickey")

    def test_comm_fallback(self):
        data = json.loads(record())
        del data["SYSLOG_IDENTIFIER"]
        data["_COMM"] = "sshd-session"
        self.assertIsNotNone(parse_line(json.dumps(data), 1))

    def test_unrelated_service_or_message_ignored(self):
        self.assertIsNone(parse_line(record(SYSLOG_IDENTIFIER="cron"), 1))
        self.assertIsNone(parse_line(record(MESSAGE="Server listening on 127.0.0.1 port 22222."), 1))

    def test_malformed_fields_counted(self):
        lines = [record(__REALTIME_TIMESTAMP="bad"), record(_HOSTNAME=None), record(MESSAGE=[70, 71]),
                 record(__REALTIME_TIMESTAMP="9" * 500), "{", "[]", record(SYSLOG_IDENTIFIER=[])]
        result = parse_lines(lines)
        self.assertEqual(result.statistics.malformed_lines, 7)
        self.assertEqual(result.events, ())

    def test_missing_timestamp_not_guessed(self):
        data = json.loads(record())
        del data["__REALTIME_TIMESTAMP"]
        with self.assertRaises(ValueError):
            parse_line(json.dumps(data), 1)
