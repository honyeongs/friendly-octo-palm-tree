"""Regression checks for privacy-safe evidence and honest result accounting."""
import copy
import json
import unittest
from pathlib import Path

from tools.portfolio_cases import PROJECT
from tools.validation_support import make_report, run_suite, validate_public_report

ROOT = Path(__file__).resolve().parents[1]
CANARY = "PRIVATE_CANARY account=PERSON_X path=C:/private/document token=DO_NOT_EXPORT"


class EvidenceTests(unittest.TestCase):
    def test_failure_text_stdout_and_stderr_never_exported(self):
        class Probe(unittest.TestCase):
            def id(self):
                return "privacy_probe.Probe.runTest"

            def runTest(self):
                import sys
                print(CANARY)
                print(CANARY, file=sys.stderr)
                self.fail(CANARY)

        report = run_suite(unittest.TestSuite([Probe()]))
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertNotIn("PRIVATE_CANARY", json.dumps(report))
        self.assertEqual(report["tests"][0]["test_id"], "privacy_probe.Probe.runTest")

    def test_unknown_skip_text_never_exported(self):
        class Probe(unittest.TestCase):
            def id(self):
                return "privacy_probe.Probe.runTest"

            def runTest(self):
                self.skipTest(CANARY)

        report = run_suite(unittest.TestSuite([Probe()]))
        self.assertEqual(report["tests"][0]["skip_category"], "other_not_published")
        self.assertNotIn("PRIVATE_CANARY", json.dumps(report))

    def test_subtest_failure_not_reported_as_success(self):
        class Probe(unittest.TestCase):
            def id(self):
                return "privacy_probe.Probe.runTest"

            def runTest(self):
                with self.subTest(private_value=CANARY):
                    self.fail(CANARY)

        report = run_suite(unittest.TestSuite([Probe()]))
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertNotIn("PRIVATE_CANARY", json.dumps(report))

    def test_class_fixture_failure_is_counted(self):
        class Probe(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError(CANARY)

            def runTest(self):
                pass

        report = run_suite(unittest.TestSuite([Probe()]))
        self.assertEqual(report["summary"]["fixture_errors"], 1)
        self.assertEqual(report["summary"]["passed"], 0)
        self.assertNotIn("PRIVATE_CANARY", json.dumps(report))

    def test_public_schema_rejects_raw_fields_and_descriptions(self):
        blank = run_suite(unittest.TestSuite())
        report = make_report(ROOT, PROJECT, blank, None, [], "2026-10-12T00:00:00+00:00")
        for field in ("raw_log", "exception", "file_path", "username", "token"):
            altered = dict(report, **{field: CANARY})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_public_report(altered)
        altered = copy.deepcopy(report)
        altered["limitations"] = [CANARY]
        with self.assertRaises(ValueError):
            validate_public_report(altered)

    def test_public_schema_rejects_inconsistent_counts(self):
        blank = run_suite(unittest.TestSuite())
        report = make_report(ROOT, PROJECT, blank, None, [], "2026-10-12T00:00:00+00:00")
        report["portfolio"]["summary"]["passed"] = 999
        with self.assertRaises(ValueError):
            validate_public_report(report)

