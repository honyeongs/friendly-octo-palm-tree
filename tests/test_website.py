"""Browser-site boundary checks without needing a browser runtime download."""
import ast
import hashlib
import importlib.util
import json
import struct
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        self.config = tomllib.loads((ROOT / "website/site.toml").read_text(encoding="utf-8"))
        spec = importlib.util.spec_from_file_location("website_bridge_under_test", ROOT / "website/bridge.py")
        self.bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bridge)

    def call(self, route, body=b"", **metadata):
        return json.loads(self.bridge._dispatch_json(route, body, json.dumps(metadata), b""))

    def test_unknown_route_is_not_an_execution_interface(self):
        result = self.call("/api/execute", b"print('INERT_TEST_ONLY')")
        self.assertEqual(result["status"], 400)
        self.assertNotIn("INERT_TEST_ONLY", json.dumps(result))

    def test_error_never_echoes_raw_exception_or_payload(self):
        if self.config["id"] == "inspector":
            result = self.call("/api/inspect", b"INERT_PRIVATE_CANARY", expected="PRIVATE_CANARY")
        elif self.config["id"] == "endpoint":
            result = self.call("/api/analyze", b"PRIVATE_CANARY", policy="baseline")
        else:
            with tempfile.TemporaryDirectory() as folder, patch.object(self.bridge, "Path", lambda name: Path(folder) / Path(name).name):
                result = self.call("/api/ssh", b"PRIVATE_CANARY")
        self.assertEqual(result["status"], 400)
        self.assertNotIn("PRIVATE_CANARY", json.dumps(result))
        self.assertNotIn("Traceback", json.dumps(result))

    def test_original_engine_is_used_and_virtual_files_cleaned(self):
        kind = self.config["id"]
        if kind == "inspector":
            data = b"ORIGINAL LOCAL TEST DATA"
            result = self.call("/api/inspect", data, name="sample.txt", expected=hashlib.sha256(data).hexdigest())
            self.assertEqual(result["data"]["integrity"]["status"], "match")
            self.assertIsNone(result["data"]["assessment"]["safe_to_open"])
        elif kind == "endpoint":
            result = self.call("/api/analyze", (ROOT / "samples/incident-chain.xml").read_bytes(), policy="baseline")
            self.assertEqual(result["data"]["alert_count"], 5)
        else:
            with tempfile.TemporaryDirectory() as folder, patch.object(self.bridge, "Path", lambda name: Path(folder) / Path(name).name):
                result = self.call("/api/ssh", (ROOT / "samples/ssh/demo.log").read_bytes(), name="sample.log")
                self.assertEqual(len(result["data"]["findings"]), 2)
                self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertEqual(result["status"], 200)

    def test_no_input_evaluation_in_bridge(self):
        tree = ast.parse((ROOT / "website/bridge.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec", "compile"})
        worker = (ROOT / "website/engine-worker.js").read_text(encoding="utf-8")
        self.assertIn('python.globals.set("_body"', worker)
        self.assertIn('bytes(_body.to_py())', worker)

    def test_original_app_icons_and_public_configuration(self):
        for size in (192, 512):
            data = (ROOT / f"website/icons/app-{size}.png").read_bytes()
            self.assertEqual(data[:8], bytes.fromhex("89504e470d0a1a0a"))
            self.assertEqual(struct.unpack(">II", data[16:24]), (size, size))
        self.assertEqual((ROOT / "website/icons/app.ico").read_bytes()[:6], bytes.fromhex("000001000100"))
        hosting = json.loads((ROOT / "website/.openai/hosting.json").read_text(encoding="utf-8"))
        self.assertEqual(hosting["static"]["directory"], "dist")
        self.assertRegex(hosting["project_id"], r"^appgprj_[a-zA-Z0-9]+$")
        self.assertEqual(len(self.config["tools"]), 3)
        self.assertTrue(self.config["url"].startswith("https://"))

    def test_runtime_pin_and_copyright_notices_are_present(self):
        from tools.build_website import RUNTIME_SHA256
        self.assertRegex(RUNTIME_SHA256, r"^[a-f0-9]{64}$")
        for name in ("PYODIDE-MPL-2.0.txt", "CPYTHON-LICENSE.txt", "EXPAT-COPYING.txt", "LIBFFI-LICENSE.txt",
                     "ZLIB-LICENSE.txt", "MUSL-COPYRIGHT.txt", "LLVM-LICENSE.txt", "LUCIDE-LICENSE.txt"):
            self.assertGreater((ROOT / "website/licenses" / name).stat().st_size, 500)
