"""Package reviewed public PWA assets into a dependency-free Sites Worker."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json",
        ".webmanifest": "application/manifest+json", ".wasm": "application/wasm",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
        ".zip": "application/zip", ".py": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
        ".rst": "text/plain; charset=utf-8", ".url": "application/octet-stream"}


def build(assets, output):
    assets, output = assets.resolve(), output.resolve()
    if assets == output or assets in output.parents or output in assets.parents:
        raise ValueError("Hosting output must be separate from input assets")
    manifest = json.loads((ROOT / "website/.openai/hosting.json").read_text(encoding="utf-8"))
    if "static" in manifest:
        raise ValueError("Header-enforcing deployment requires Worker hosting")
    inventory = json.loads((assets / "build-inventory.json").read_text(encoding="utf-8"))
    expected = set(inventory["files"]) | {"sw.js", "build-inventory.json"}
    records = {}
    for name in sorted(expected - {"_headers"}):
        path = (assets / name).resolve()
        if not path.is_relative_to(assets) or not path.is_file() or path.is_symlink():
            raise ValueError("Invalid public asset")
        data = path.read_bytes()
        if name in inventory["files"]:
            if hashlib.sha256(data).hexdigest() != inventory["files"][name]:
                raise ValueError("Public asset differs from build inventory")
        records["/" + name] = [MIME.get(path.suffix, "application/octet-stream"),
            base64.b64encode(gzip.compress(data, compresslevel=9, mtime=0)).decode("ascii")]
    # Never package unrelated leftovers or secrets from a reused output directory.
    allowed = {"server/index.js", ".openai/hosting.json"}
    if output.exists() and any(p.is_symlink() or (p.is_file() and p.relative_to(output).as_posix() not in allowed) for p in output.rglob("*")):
        raise ValueError("Hosting output contains unrelated files")
    server = output / "server"
    server.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "website/hosting-worker.mjs").read_text(encoding="utf-8")
    (server / "index.js").write_text("const SITE_ASSETS = " + json.dumps(records, separators=(",", ":")) + ";\n" +
        source + "\nexport default createAssetWorker(SITE_ASSETS);\n", encoding="utf-8", newline="\n")
    metadata = output / ".openai"
    metadata.mkdir(exist_ok=True)
    (metadata / "hosting.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"public_assets": len(records), "worker_bytes": (server / "index.js").stat().st_size}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "website/dist")
    parser.add_argument("--output", type=Path, default=ROOT / "website/hosting-dist")
    args = parser.parse_args()
    build(args.assets, args.output)
