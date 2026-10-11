import json
import unittest

from tests.test_cli import ROOT, run_cli


class ExtendedCliTests(unittest.TestCase):
    def test_native_journal_and_text_equivalent(self):
        text = run_cli("analyze-ssh", "samples/ssh/correlated.log")
        native = run_cli("analyze-ssh", "samples/ssh/journal.jsonl")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertEqual(native.returncode, 0, native.stderr)
        a, b = json.loads(text.stdout), json.loads(native.stdout)
        self.assertEqual(a["findings"], b["findings"])
        self.assertEqual(a["success_after_failures"], b["success_after_failures"])

    def test_explicit_format(self):
        result = run_cli("analyze-ssh", "samples/ssh/journal.jsonl", "--format", "journal")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["input_format"], "journal")

    def test_capture_command(self):
        result = run_cli("analyze-pcap", "samples/packets/demo.pcapng", "--server-ip", "192.0.2.100")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["network"]["statistics"]["connection_attempts"], 6)

    def test_combined_command(self):
        result = run_cli("analyze-ssh", "samples/ssh/journal.jsonl", "--pcap", "samples/packets/demo.pcap", "--server-ip", "192.0.2.100")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["network"]["finding_links"][0]["connection_attempts"], 5)

    def test_missing_mapping_and_invalid_extension_options(self):
        for args in (("--pcap", "samples/packets/demo.pcap"), ("--server-ip", "192.0.2.100"),
                     ("--success-window-seconds", "0"), ("--server-port", "65536"),
                     ("--packet-margin-seconds", "-1")):
            with self.subTest(args=args):
                result = run_cli("analyze-ssh", "samples/ssh/demo.log", *args)
                self.assertEqual(result.returncode, 2)

    def test_capture_itself_cannot_be_overwritten(self):
        path = ROOT / "samples/packets/demo.pcap"
        original = path.read_bytes()
        result = run_cli("analyze-ssh", "samples/ssh/journal.jsonl", "--pcap", path,
                         "--server-ip", "192.0.2.100", "--output", path, "--overwrite")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_bytes(), original)
