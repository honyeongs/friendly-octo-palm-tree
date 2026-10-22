"""Protect the release allowlist, source checksums and separate hosting output."""
import base64
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.build_hosting import build


class HostingBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets, self.output = self.root / "assets", self.root / "worker"
        self.assets.mkdir()
        (self.assets / "index.html").write_bytes(b"INERT PUBLIC PAGE")
        (self.assets / "sw.js").write_bytes(b"/* public cache */")
        (self.assets / "_headers").write_bytes(b"legacy metadata")
        self.inventory = {"files": {name: hashlib.sha256((self.assets / name).read_bytes()).hexdigest()
                                   for name in ("index.html", "_headers")}}
        self.save_inventory()

    def save_inventory(self):
        (self.assets / "build-inventory.json").write_text(json.dumps(self.inventory), encoding="utf-8")

    def test_packages_only_reviewed_assets_and_original_bytes(self):
        (self.assets / ".env").write_bytes(b"INERT_PRIVATE_CANARY")
        build(self.assets, self.output)
        line = (self.output / "server/index.js").read_text(encoding="utf-8").splitlines()[0]
        records = json.loads(line.removeprefix("const SITE_ASSETS = ").removesuffix(";"))
        self.assertEqual(set(records), {"/index.html", "/sw.js", "/build-inventory.json"})
        self.assertEqual(gzip.decompress(base64.b64decode(records["/index.html"][1])), b"INERT PUBLIC PAGE")
        self.assertEqual(records["/index.html"][0], "text/html; charset=utf-8")
        self.assertNotIn("static", json.loads((self.output / ".openai/hosting.json").read_text(encoding="utf-8")))

    def test_changed_asset_fails_before_packaging(self):
        (self.assets / "index.html").write_bytes(b"CHANGED")
        with self.assertRaises(ValueError):
            build(self.assets, self.output)
        self.assertFalse(self.output.exists())

    def test_inventory_cannot_escape_public_directory(self):
        self.inventory["files"]["../outside"] = hashlib.sha256(b"INERT").hexdigest()
        (self.root / "outside").write_bytes(b"INERT")
        self.save_inventory()
        with self.assertRaises(ValueError):
            build(self.assets, self.output)

    def test_input_and_output_must_not_overlap(self):
        with self.assertRaises(ValueError):
            build(self.assets, self.assets / "nested")
        with self.assertRaises(ValueError):
            build(self.assets, self.root)

    def test_unrelated_output_is_preserved_and_rejected(self):
        self.output.mkdir()
        marker = self.output / "private-note"
        marker.write_bytes(b"INERT_PRIVATE_CANARY")
        with self.assertRaises(ValueError):
            build(self.assets, self.output)
        self.assertEqual(marker.read_bytes(), b"INERT_PRIVATE_CANARY")
