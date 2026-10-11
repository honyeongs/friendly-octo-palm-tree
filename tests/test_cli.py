import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "run.py"), *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )


class CliTests(unittest.TestCase):
    def test_sample_matches_independent_expected_summary(self):
        expected = json.loads((ROOT / "samples/ssh/expected-summary.json").read_text(encoding="utf-8"))
        for filename, summary in expected.items():
            with self.subTest(filename=filename):
                result = run_cli("analyze-ssh", ROOT / "samples/ssh" / filename)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["source"], filename)
                self.assertEqual(report["schema_version"], "1.1")
                for key, value in summary.items():
                    if key != "findings":
                        self.assertEqual(report["statistics"][key], value)
                findings = [{
                    "host": item["host"], "source_ip": item["source_ip"],
                    "failure_count": item["failure_count"],
                    "peak_window_failures": item["peak_window_failures"],
                    "line_numbers": [event["line_number"] for event in item["evidence"]],
                } for item in report["findings"]]
                self.assertEqual(findings, summary["findings"])
                self.assertEqual(report["statistics"]["finding_count"], len(findings))
                if filename == "demo.log":
                    self.assertIn("Warning", result.stderr)
                    self.assertEqual(report["findings"][0]["start_time"], "2026-10-11T00:01:00Z")
                    self.assertEqual(report["findings"][0]["usernames"], ["admin", "alice", "root"])

    def test_output_file_and_overwrite_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = ("analyze-ssh", "samples/ssh/demo.log", "--output", output)
            result = run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            original = output.read_bytes()
            refused = run_cli(*args)
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(output.read_bytes(), original)
            allowed = run_cli(*args, "--overwrite")
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual(output.read_bytes(), original)

    def test_cannot_overwrite_input_even_with_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.log"
            path.write_bytes((ROOT / "samples/ssh/demo.log").read_bytes())
            before = path.read_bytes()
            result = run_cli("analyze-ssh", path, "--output", path, "--overwrite")
            self.assertEqual(result.returncode, 2)
            self.assertIn("input log", result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_hardlink_to_input_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.log", Path(directory) / "alias.json"
            source.write_bytes((ROOT / "samples/ssh/demo.log").read_bytes())
            try:
                os.link(source, output)
            except OSError as error:
                self.skipTest(f"Hard links unavailable: {error}")
            before = source.read_bytes()
            result = run_cli("analyze-ssh", source, "--output", output, "--overwrite")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_bytes(), before)

    def test_invalid_arguments(self):
        for option, value in (("--threshold", "0"), ("--threshold", "-1"),
                              ("--threshold", "nan"), ("--window-seconds", "0"),
                              ("--window-seconds", "86401"), ("--window-seconds", "1.5")):
            with self.subTest(option=option, value=value):
                result = run_cli("analyze-ssh", "samples/ssh/demo.log", option, value)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_missing_input(self):
        result = run_cli("analyze-ssh", "samples/ssh/does-not-exist.log")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", result.stderr)

    def test_directory_input(self):
        self.assertEqual(run_cli("analyze-ssh", "samples/ssh").returncode, 2)

    def test_missing_output_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli("analyze-ssh", "samples/ssh/demo.log", "--output", Path(directory) / "missing/report.json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")

    def test_empty_or_unsupported_input_creates_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.log", Path(directory) / "report.json"
            for content in ("", "unrelated\n", "Oct 11 00:00:00 lab sshd[1]: Failed password for alice from 192.0.2.1 port 50001 ssh2\n"):
                with self.subTest(content=content):
                    source.write_text(content, encoding="utf-8")
                    result = run_cli("analyze-ssh", source, "--output", output)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("No supported SSH", result.stderr)
                    self.assertFalse(output.exists())

    def test_invalid_utf8_creates_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.log", Path(directory) / "report.json"
            source.write_bytes(b"\xff\xfeinvalid")
            result = run_cli("analyze-ssh", source, "--output", output)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_utf8_bom_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.log"
            source.write_text((ROOT / "samples/ssh/demo.log").read_text(encoding="utf-8"), encoding="utf-8-sig")
            result = run_cli("analyze-ssh", source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["statistics"]["finding_count"], 2)

    def test_output_is_deterministic(self):
        first = run_cli("analyze-ssh", "samples/ssh/demo.log")
        second = run_cli("analyze-ssh", "samples/ssh/demo.log")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_help_version_and_required_subcommand(self):
        self.assertIn("analyze-ssh", run_cli("--help").stdout)
        self.assertEqual(run_cli("--version").stdout.strip(), "netsec 0.2.0")
        self.assertEqual(run_cli().returncode, 2)

    def test_custom_threshold_changes_sample_findings(self):
        result = run_cli("analyze-ssh", "samples/ssh/demo.log", "--threshold", "6")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_installed_module_entrypoint(self):
        result = subprocess.run(
            [sys.executable, "-m", "netsec", "analyze-ssh", "samples/ssh/normal.log"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], [])
