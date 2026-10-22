import assert from "node:assert/strict";
import {gzipSync, gunzipSync} from "node:zlib";
import {test} from "node:test";
import {createAssetWorker, SECURITY_HEADERS} from "../../website/hosting-worker.mjs";
const encode = text => gzipSync(Buffer.from(text)).toString("base64");

test("precompressed responses explicitly disable Workers automatic recompression", async () => {
  const NativeResponse = globalThis.Response;
  let encoding;
  globalThis.Response = class extends NativeResponse {
    constructor(body, options) { super(body, options); encoding = options.encodeBody; }
  };
  try {
    await worker.fetch(new Request("https://portfolio.example.test/"));
    assert.equal(encoding, "manual");
  } finally { globalThis.Response = NativeResponse; }
});
const worker = createAssetWorker({"/index.html": ["text/html; charset=utf-8", encode("INERT PUBLIC PAGE")],
  "/engine-worker.js": ["text/javascript; charset=utf-8", encode("self.onmessage = () => {};")],
  "/sw.js": ["text/javascript; charset=utf-8", encode("/* public cache only */")]});

test("CSP, framing, nosniff and no-referrer protect documents, workers and errors", async () => {
  for (const [path, status] of [["/", 200], ["/engine-worker.js", 200], ["/unknown", 404]]) {
    const response = await worker.fetch(new Request("https://portfolio.example.test" + path));
    assert.equal(response.status, status);
    for (const [name, value] of Object.entries(SECURITY_HEADERS)) assert.equal(response.headers.get(name), value);
    assert.ok(response.headers.get("content-security-policy").includes("frame-ancestors 'none'"));
  }
});
test("compressed assets round-trip without executing or modifying their content", async () => {
  const response = await worker.fetch(new Request("https://portfolio.example.test/"));
  assert.equal(response.headers.get("content-encoding"), "gzip");
  assert.equal(gunzipSync(Buffer.from(await response.arrayBuffer())).toString(), "INERT PUBLIC PAGE");
});
test("HEAD is bodyless and unsupported methods reject input without reading it", async () => {
  const head = await worker.fetch(new Request("https://portfolio.example.test/", {method: "HEAD"}));
  assert.equal(head.status, 200); assert.equal((await head.arrayBuffer()).byteLength, 0);
  const rejected = await worker.fetch(new Request("https://portfolio.example.test/api/analyze", {method: "POST", body: "PRIVATE_CANARY"}));
  assert.equal(rejected.status, 405); assert.equal(rejected.headers.get("allow"), "GET, HEAD");
  assert.equal(rejected.headers.get("cache-control"), "no-store");
  assert.equal((await rejected.text()).includes("PRIVATE_CANARY"), false);
});
test("only the fixed public allowlist is accessible", async () => {
  for (const path of ["/.env", "/__proto__", "/%2e%2e/secret", "/server/index.js"]) {
    const response = await worker.fetch(new Request("https://portfolio.example.test" + path));
    assert.equal(response.status, 404);
  }
  const sw = await worker.fetch(new Request("https://portfolio.example.test/sw.js"));
  assert.equal(sw.headers.get("service-worker-allowed"), "/");
});
