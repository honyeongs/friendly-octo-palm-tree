import random
import unittest

from netsec.detectors.repeated_failures import detect_repeated_failures
from netsec.parsers.ssh import parse_lines
from tests.helpers import events_at, log_line


class RepeatedFailureTests(unittest.TestCase):
    def test_four_failures_do_not_trigger(self):
        self.assertEqual(detect_repeated_failures(events_at([0, 10, 20, 30])), ())

    def test_five_failures_trigger(self):
        finding, = detect_repeated_failures(events_at([0, 10, 20, 30, 40]))
        self.assertEqual(len(finding.evidence), 5)
        self.assertEqual(finding.peak_window_failures, 5)

    def test_exactly_sixty_seconds_included(self):
        self.assertEqual(len(detect_repeated_failures(events_at([0, 15, 30, 45, 60]))), 1)

    def test_over_sixty_seconds_excluded(self):
        self.assertEqual(detect_repeated_failures(events_at([0, 15, 30, 45, 60.000001])), ())

    def test_unsorted_input(self):
        finding, = detect_repeated_failures(events_at([40, 0, 30, 10, 20]))
        self.assertEqual([item.line_number for item in finding.evidence], [2, 4, 5, 3, 1])

    def test_different_ips_and_hosts_are_separate(self):
        lines = [log_line(index * 5, ip=ip, host=host)
                 for ip, host in (("192.0.2.10", "lab"), ("192.0.2.11", "lab"), ("192.0.2.10", "other"))
                 for index in range(4)]
        self.assertEqual(detect_repeated_failures(parse_lines(lines).events), ())

    def test_success_does_not_count_or_reset(self):
        lines = [log_line(index * 10) for index in range(5)]
        lines.insert(3, log_line(25, outcome="Accepted"))
        finding, = detect_repeated_failures(parse_lines(lines).events)
        self.assertEqual(len(finding.evidence), 5)

    def test_same_timestamp_and_duplicate_lines_count(self):
        finding, = detect_repeated_failures(events_at([0, 0, 0, 0, 0]))
        self.assertEqual([item.line_number for item in finding.evidence], [1, 2, 3, 4, 5])

    def test_overlapping_windows_merge_without_duplicate_evidence(self):
        finding, = detect_repeated_failures(events_at([0, 10, 20, 30, 40, 50, 60, 70]))
        self.assertEqual(len(finding.evidence), 8)
        self.assertEqual(finding.peak_window_failures, 7)

    def test_independent_episodes(self):
        findings = detect_repeated_failures(events_at([0, 1, 2, 3, 4, 120, 121, 122, 123, 124]))
        self.assertEqual([len(item.evidence) for item in findings], [5, 5])

    def test_ipv6_equivalent_spellings_group_together(self):
        lines = [log_line(index, ip="2001:db8::1" if index % 2 else "2001:0db8::1") for index in range(5)]
        finding, = detect_repeated_failures(parse_lines(lines).events)
        self.assertEqual(finding.source_ip, "2001:db8::1")

    def test_custom_parameters(self):
        self.assertEqual(len(detect_repeated_failures(events_at([0, 1, 2]), window_seconds=2, threshold=3)), 1)

    def test_bad_parameters(self):
        for options in ({"window_seconds": 0}, {"window_seconds": 86401},
                        {"window_seconds": 1.5}, {"threshold": 0}, {"threshold": 1.5}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                detect_repeated_failures((), **options)

    def test_large_burst_has_one_finding(self):
        finding, = detect_repeated_failures(events_at([0] * 10000))
        self.assertEqual((len(finding.evidence), finding.peak_window_failures), (10000, 10000))

    def test_matches_independent_window_oracle(self):
        rng = random.Random(42)
        for _ in range(100):
            seconds = [rng.randint(0, 200) for _ in range(30)]
            events = events_at(seconds)
            ordered = sorted(events, key=lambda item: (item.timestamp, item.line_number))
            qualifying = []
            for right, event in enumerate(ordered):
                window = [item for item in ordered[:right + 1]
                          if (event.timestamp - item.timestamp).total_seconds() <= 30]
                if len(window) >= 5:
                    qualifying.append(window)
            expected_lines = {item.line_number for window in qualifying for item in window}
            findings = detect_repeated_failures(events, window_seconds=30, threshold=5)
            actual_lines = {item.line_number for finding in findings for item in finding.evidence}
            self.assertEqual(actual_lines, expected_lines)
            self.assertEqual(sum(len(item.evidence) for item in findings), len(actual_lines))
