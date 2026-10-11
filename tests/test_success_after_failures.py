import unittest

from netsec.detectors.success_after_failures import correlate_successes
from netsec.parsers.ssh import parse_lines
from tests.helpers import log_line


def scenario(success=50, **success_options):
    return parse_lines([log_line(value) for value in [0, 10, 20, 30, 40]] +
                       [log_line(success, outcome="Accepted", **success_options)]).events


class SuccessCorrelationTests(unittest.TestCase):
    def test_matching_user_and_burst(self):
        item, = correlate_successes(scenario())
        self.assertEqual(item["username"], "alice")
        self.assertEqual(item["seconds_after_last_failure"], 10)
        self.assertEqual(item["success_event"].line_number, 6)

    def test_exact_success_boundary(self):
        self.assertEqual(len(correlate_successes(scenario(340))), 1)
        self.assertEqual(correlate_successes(scenario(340.000001)), ())

    def test_other_ip_host_or_user_not_correlated(self):
        for options in ({"username": "bob"}, {"host": "other"}, {"ip": "192.0.2.11"}):
            with self.subTest(options=options):
                self.assertEqual(correlate_successes(scenario(**options)), ())

    def test_success_before_failures_not_correlated(self):
        self.assertEqual(correlate_successes(scenario(-1)), ())

    def test_mixed_user_aggregate_does_not_count_as_same_user_burst(self):
        lines = [log_line(value, username="alice" if index < 3 else "bob")
                 for index, value in enumerate([0, 10, 20, 30, 40])]
        lines.append(log_line(50, outcome="Accepted"))
        self.assertEqual(correlate_successes(parse_lines(lines).events), ())

    def test_success_resets_and_only_first_success_is_correlated(self):
        events = scenario() + parse_lines([log_line(55, outcome="Accepted")]).events
        self.assertEqual(len(correlate_successes(events)), 1)
        lines = [log_line(0), log_line(10), log_line(15, outcome="Accepted"),
                 log_line(20), log_line(30), log_line(40), log_line(50, outcome="Accepted")]
        self.assertEqual(correlate_successes(parse_lines(lines).events), ())

    def test_isolated_late_failure_does_not_extend_old_burst(self):
        lines = [log_line(value) for value in [0, 10, 20, 30, 40, 330]]
        lines.append(log_line(350, outcome="Accepted"))
        self.assertEqual(correlate_successes(parse_lines(lines).events), ())

    def test_unsorted_input(self):
        self.assertEqual(len(correlate_successes(reversed(scenario()))), 1)

    def test_invalid_windows(self):
        for options in ({"threshold": 0}, {"success_window_seconds": 0}, {"window_seconds": 86401}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                correlate_successes((), **options)
