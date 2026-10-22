"""Build a self-hosted, browser-local PWA from the original analysis modules."""
import argparse
import hashlib
import html
import importlib.util
import json
import shutil
import struct
import tarfile
import tomllib
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHA256 = "ab08aafc11a3c9a0fe73825eb2cec78bda9464348dd17414e7ec0132ef3451e8"
RUNTIME_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".json", ".xml", ".txt", ".md", ".svg"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SiteHTML(HTMLParser):
    def __init__(self, extra):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.extra = extra

    def handle_starttag(self, tag, attrs):
        self.parts.append(self.get_starttag_text())
        if tag == "main":
            self.parts.append(self.extra)

    def handle_startendtag(self, tag, attrs):
        self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "head":
            self.parts.append('<meta name="theme-color" content="#146c57"><meta name="referrer" content="no-referrer"><link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icons/app-192.png"><link rel="stylesheet" href="/site.css"><script type="module" src="/pwa.js"></script>')
            if self.extra:
                self.parts.append('<script type="module" src="/analyze-panel.js"></script>')
            self.parts.append('<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\' \'wasm-unsafe-eval\'; worker-src \'self\'; style-src \'self\'; img-src \'self\' data:; connect-src \'self\'; object-src \'none\'; base-uri \'none\'; form-action \'none\'">')
        self.parts.append("</" + tag + ">")

    def handle_data(self, value):
        self.parts.append(value)

    def handle_entityref(self, value):
        self.parts.append("&" + value + ";")

    def handle_charref(self, value):
        self.parts.append("&#" + value + ";")

    def handle_decl(self, value):
        self.parts.append("<!" + value + ">")

    def handle_comment(self, value):
        self.parts.append("<!--" + value + "-->")


def write_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def engine_archive(config, destination):
    package = config["package"]
    source = ROOT / "src" / package
    paths = [p for p in source.glob("*.py") if p.name not in {"server.py", "http_security.py", "cli.py", "__main__.py"}]
    if package == "netsec":
        paths = [source / name for name in ("__init__.py", "models.py", "analysis.py")]
        paths += [p for directory in ("parsers", "detectors", "reporters", "packets") for p in (source / directory).rglob("*.py")]
    entries = [(p.relative_to(ROOT / "src").as_posix(), p.read_bytes().replace(b"\r\n", b"\n")) for p in paths]
    if package == "netsec":
        spec = importlib.util.find_spec("dpkt")
        if spec is None or not spec.origin:
            raise ValueError("Install .[packets] in the build environment")
        dpkt_root = Path(spec.origin).parent
        entries += [("dpkt/" + p.relative_to(dpkt_root).as_posix(), p.read_bytes().replace(b"\r\n", b"\n")) for p in dpkt_root.glob("*.py")]
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def build(runtime_archive, output):
    config = tomllib.loads((ROOT / "website/site.toml").read_text(encoding="utf-8"))
    output = output.resolve()
    source_dir = ROOT / "website"
    if output in {ROOT, source_dir} or ROOT / "src" in output.parents:
        raise ValueError("Output must be a separate build directory")
    if digest(runtime_archive.read_bytes()) != RUNTIME_SHA256:
        raise ValueError("Runtime archive differs from reviewed Pyodide 0.29.5")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "src" / config["package"] / "web", output, dirs_exist_ok=True)
    for name in ("engine-client.js", "engine-worker.js", "pwa.js", "site.css", "bridge.py"):
        shutil.copyfile(source_dir / name, output / name)
    if config["id"] != "netsec":
        shutil.copyfile(source_dir / "transport.js", output / "transport.js")
    else:
        shutil.copyfile(source_dir / "analyze-panel.js", output / "analyze-panel.js")
    shutil.copytree(source_dir / "icons", output / "icons", dirs_exist_ok=True)
    shutil.copytree(source_dir / "licenses", output / "licenses", dirs_exist_ok=True)
    dpkt_notices = ROOT / "third_party/dpkt"
    if dpkt_notices.is_dir():
        shutil.copytree(dpkt_notices, output / "licenses/dpkt", dirs_exist_ok=True)
    runtime_dir = output / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    with tarfile.open(runtime_archive, "r:bz2") as archive:
        for name in RUNTIME_FILES:
            member = archive.getmember("pyodide/" + name)
            if not member.isfile() or member.size > 16 * 1024 * 1024:
                raise ValueError("Invalid runtime member")
            (runtime_dir / name).write_bytes(archive.extractfile(member).read())
    engine_archive(config, output / "engine.zip")
    parser = SiteHTML((source_dir / "raw-form.html").read_text(encoding="utf-8") if config["id"] == "netsec" else "")
    parser.feed((output / "index.html").read_text(encoding="utf-8"))
    write_text(output / "index.html", "".join(parser.parts))
    public_config = {"id": config["id"], "title": config["title"], "repository": config["repository"], "tools": config["tools"]}
    write_text(output / "site-config.json", json.dumps(public_config, ensure_ascii=True))
    manifest = {"id": "/", "name": config["title"], "short_name": config["short_name"], "lang": "ko",
                "start_url": "/", "scope": "/", "display": "standalone", "background_color": "#ffffff",
                "theme_color": config["color"], "prefer_related_applications": False,
                "icons": [{"src": f"/icons/app-{size}.png", "type": "image/png", "sizes": f"{size}x{size}", "purpose": "any maskable"} for size in (192, 512)]}
    write_text(output / "manifest.webmanifest", json.dumps(manifest, ensure_ascii=True, indent=2))
    write_text(output / "windows-shortcut.url", "[InternetShortcut]\nURL=" + config["url"] + "/\n")
    samples = output / "samples"
    samples.mkdir(exist_ok=True)
    if config["id"] == "netsec":
        shutil.copyfile(ROOT / "samples/ssh/demo.log", samples / "demo.log")
    elif config["id"] == "inspector":
        with zipfile.ZipFile(samples / "example.zip", "w") as archive:
            for name, data in (("readme.txt", b"ORIGINAL SYNTHETIC DEMO"), ("../escape.exe", b"INERT METADATA TEST"), ("inner.zip", b"INERT PLACEHOLDER")):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                archive.writestr(info, data)
    else:
        shutil.copyfile(ROOT / "samples/incident-chain.xml", samples / "incident-chain.xml")
    legal_links = "".join(f'<li><a href="/licenses/{html.escape(p.relative_to(output / "licenses").as_posix())}">{html.escape(p.name)}</a></li>'
                          for p in sorted((output / "licenses").rglob("*")) if p.is_file())
    page_head = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/site.css"><title>'
    page_style = '<body><main class="legal-page">'
    write_text(output / "licenses.html", page_head + '라이선스·출처</title>' + page_style +
               '<h1>라이선스·출처</h1><p>웹 런타임 Pyodide 0.29.5(MPL-2.0), CPython 3.13.2 및 포함 구성요소의 고지입니다. 런타임은 수정하지 않았습니다.</p><p>Pyodide 원본 소스: <a href="https://github.com/pyodide/pyodide/tree/0.29.5">해당 버전 소스</a>. Python 원본: <a href="https://github.com/python/cpython/tree/v3.13.2">CPython 3.13.2</a>.</p><p>아이콘은 Lucide 원본 도형에서 앱 아이콘용 색상·배경·크기를 조정했습니다. 원본 고지는 아래에 포함합니다. NetSec의 PCAP 해석은 dpkt를 사용합니다.</p><ul>' +
               legal_links + '</ul><p>자체 코드에 새로운 재사용 라이선스를 자동 부여하지 않습니다. 이 목록은 법률 자문이나 무침해 보증이 아닙니다.</p><a href="/">분석 화면으로</a></main></body></html>')
    write_text(output / "privacy.html", page_head + '개인정보</title>' + page_style +
               '<h1>개인정보와 처리 범위</h1><p>선택한 파일·로그·보고서는 이 브라우저의 Worker와 메모리 파일시스템에서 분석합니다. 분석 요청을 서버로 보내거나 원본을 서버에 저장하지 않습니다. 분석 중 새로고침·취소·세션 지우기는 작업을 종료합니다.</p><p>오프라인 캐시는 공개 앱 코드·런타임·합성 예제만 포함합니다. 선택한 파일·보고서·계정·토큰은 캐시하지 않습니다. 브라우저나 운영체제 자체의 메모리·캐시 정책까지 삭제를 보증하지는 않습니다.</p><p>웹사이트 접속과 공개 자산 다운로드 과정에서 호스팅 제공자는 IP·접속 시각 같은 일반 접속 정보를 처리할 수 있습니다. 별도 분석·광고·외부 CDN 스크립트는 넣지 않았습니다.</p><p>내보내기는 사용자가 누를 때만 로컬 파일로 저장합니다. 내보낸 원본 보고서에는 개인정보가 포함될 수 있으므로 그대로 공개하지 마세요.</p><p>백신·상용 EDR·안전 인증이 아닙니다. NetSec 웹은 오프라인 SSH·PCAP 분석 도구이며 기존 로컬 SaaS의 회원·청구·서버 운영을 인터넷으로 노출하지 않습니다.</p><a href="/">분석 화면으로</a></main></body></html>')
    write_text(output / "_headers", "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  X-Frame-Options: DENY\n  Content-Security-Policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'\n")
    inventory = {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name not in {"sw.js", "build-inventory.json"}}
    version = digest(("response-headers-v1:" + json.dumps(inventory, sort_keys=True)).encode())[:16]
    assets = ["/"] + ["/" + name for name in inventory if name != "_headers"]
    sw = "const CACHE = " + json.dumps(config["id"] + "-app-" + version) + ";\nconst ASSETS = " + json.dumps(assets) + ";\n"
    sw += """self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith(CACHE.split("-app-")[0] + "-app-") && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !ASSETS.includes(url.pathname)) return;
  event.respondWith(caches.open(CACHE).then(async cache => {
    if (url.pathname === "/" || url.pathname === "/index.html") {
      try { return await fetch(event.request); } catch { return (await cache.match(event.request, {ignoreSearch: true})) || await cache.match("/"); }
    }
    return (await cache.match(event.request, {ignoreSearch: true})) || fetch(event.request);
  }));
});
"""
    write_text(output / "sw.js", sw)
    write_text(output / "build-inventory.json", json.dumps({"runtime": "pyodide-0.29.5", "runtime_archive_sha256": RUNTIME_SHA256, "version": version, "files": inventory}, indent=2))
    print(json.dumps({"app": config["id"], "version": version, "files": len(inventory), "bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "website/dist")
    args = parser.parse_args()
    build(args.runtime_archive, args.output)
