import unittest
from datetime import timezone

from netsec.parsers.ssh import parse_line, parse_lines
from tests.helpers import log_line


class SshParserTests(unittest.TestCase):
    def test_failed_password_preserves_source_and_line(self):
        event = parse_line(log_line(), 7)
        self.assertEqual((event.host, event.source_ip, event.username), ("lab", "192.0.2.10", "alice"))
        self.assertEqual((event.outcome, event.method, event.port, event.line_number),
                         ("failed", "password", 50001, 7))

    def test_invalid_user(self):
        self.assertTrue(parse_line(log_line(invalid=True), 1).invalid_user)

    def test_all_documented_methods_and_outcomes(self):
        for outcome in ("Failed", "Accepted"):
            for method in ("password", "publickey", "keyboard-interactive/pam"):
                with self.subTest(outcome=outcome, method=method):
                    event = parse_line(log_line(outcome=outcome, method=method), 1)
                    self.assertEqual(event.outcome, outcome.lower())
                    self.assertEqual(event.method, method)

    def test_publickey_suffix(self):
        event = parse_line(log_line(outcome="Accepted", method="publickey") + " ED25519 SHA256:demo", 1)
        self.assertEqual(event.outcome, "accepted")

    def test_offset_normalized_to_utc(self):
        event = parse_line(log_line().replace("00:00:00+00:00", "09:00:00+09:00"), 1)
        self.assertEqual(event.timestamp.hour, 0)
        self.assertEqual(event.timestamp.tzinfo, timezone.utc)

    def test_z_timestamp(self):
        event = parse_line(log_line().replace("+00:00", "Z"), 1)
        self.assertEqual(event.timestamp.utcoffset().total_seconds(), 0)

    def test_ipv6_canonicalized(self):
        event = parse_line(log_line(ip="2001:0db8:0000:0000:0000:0000:0000:0001"), 1)
        self.assertEqual(event.source_ip, "2001:db8::1")

    def test_sshd_session_process(self):
        event = parse_line(log_line().replace("sshd[123]", "sshd-session[123]"), 1)
        self.assertIsNotNone(event)

    def test_invalid_auth_lines_rejected(self):
        base = log_line()
        cases = [
            base.replace("+00:00", ""),
            base.replace("2026-10-11", "2026-99-11"),
            base.replace("192.0.2.10", "999.0.0.1"),
            base.replace("50001", "0"),
            base.replace("50001", "65536"),
            base.replace("50001", "no-port"),
            base.replace("192.0.2.10", "fe80::1%eth0"),
            base.replace("from 192.0.2.10 ", ""),
            log_line(outcome="Accepted", invalid=True),
            "Oct 11 00:00:00 lab sshd[123]: Failed password for alice from 192.0.2.10 port 50001 ssh2",
        ]
        for line in cases:
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_line(line, 1)

    def test_irrelevant_logs_ignored(self):
        for line in ("unrelated", "", log_line().replace("Failed password", "Disconnected")):
            self.assertIsNone(parse_line(line, 1))

    def test_statistics_partition_every_line(self):
        parsed = parse_lines([
            "\n", "unrelated", log_line(), log_line(outcome="Accepted"),
            log_line().replace("192.0.2.10", "bad-ip"),
        ])
        stats = parsed.statistics
        self.assertEqual((stats.total_lines, stats.blank_lines, stats.ignored_lines,
                          stats.malformed_lines, stats.parsed_events), (5, 1, 1, 1, 2))
        self.assertEqual(stats.malformed_line_numbers, (5,))
        self.assertEqual((stats.failed_events, stats.accepted_events), (1, 1))
