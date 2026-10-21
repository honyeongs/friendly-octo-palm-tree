"""Keep release pins, SBOM and preserved upstream notices consistent."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SupplyChainTests(unittest.TestCase):
    def setUp(self):
        self.packages = json.loads((ROOT / "docs/DEPENDENCIES.json").read_text(encoding="utf-8"))["packages"]
        self.pins = dict(line.split("==") for line in
                         (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8").splitlines()
                         if line and not line.startswith("#"))

    def test_inventory_matches_exact_pins(self):
        self.assertEqual(len(self.packages), len(self.pins))
        self.assertEqual({p["name"]: p["version"] for p in self.packages}, self.pins)

    def test_sbom_matches_pins_and_package_urls(self):
        components = json.loads((ROOT / "docs/SBOM.cdx.json").read_text(encoding="utf-8"))["components"]
        self.assertEqual(len(components), len(self.pins))
        self.assertEqual({p["name"]: p["version"] for p in components}, self.pins)
        for item in components:
            self.assertEqual(item["purl"], f"pkg:pypi/{item['name']}@{item['version']}")

    def test_original_notice_hashes(self):
        for package in self.packages:
            self.assertTrue(package["notices"], package["name"])
            for notice in package["notices"]:
                with self.subTest(package=package["name"], notice=notice["path"]):
                    path = (ROOT / notice["path"]).resolve()
                    self.assertTrue(path.is_relative_to(ROOT / "third_party"))
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), notice["sha256"])

    def test_certifi_security_floor(self):
        # GHSA-6q48-6c7w-9gw2: certifi uses date-based numeric release versions.
        self.assertGreaterEqual(tuple(map(int, self.pins["certifi"].split("."))), (2026, 10, 19))
