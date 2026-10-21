/* Only code-owned routes reach Python; file bytes are never evaluated as source. */
let python;
let bridgeReady;
let queue = Promise.resolve();
async function boot() {
  if (bridgeReady) return bridgeReady;
  bridgeReady = (async () => {
    self.postMessage({stage: "Python 엔진 다운로드 중 · 처음 한 번만 준비합니다"});
    importScripts("/runtime/pyodide.js");
    python = await loadPyodide({indexURL: new URL("/runtime/", self.location.href).href,
      stdout: () => {}, stderr: () => {}});
    const [archive, bridge] = await Promise.all([
      fetch("/engine.zip", {credentials: "omit"}).then(r => {if (!r.ok) throw new Error("Engine unavailable"); return r.arrayBuffer();}),
      fetch("/bridge.py", {credentials: "omit"}).then(r => {if (!r.ok) throw new Error("Bridge unavailable"); return r.text();}),
    ]);
    python.FS.writeFile("/engine.zip", new Uint8Array(archive));
    python.runPython("import sys; sys.path.insert(0, '/engine.zip')");
    python.runPython(bridge);
  })();
  return bridgeReady;
}
self.onmessage = ({data}) => {
  queue = queue.then(async () => {
    try {
      await boot();
      python.globals.set("_route", data.route);
      python.globals.set("_body", new Uint8Array(data.bytes));
      python.globals.set("_metadata", JSON.stringify(data.metadata));
      python.globals.set("_auxiliary", new Uint8Array(data.auxiliary || new ArrayBuffer(0)));
      const result = JSON.parse(python.runPython("_dispatch_json(_route, bytes(_body.to_py()), _metadata, bytes(_auxiliary.to_py()))"));
      self.postMessage({id: data.id, ok: true, result});
    } catch {
      self.postMessage({id: data.id, ok: false, error: "분석 엔진 오류입니다. 파일 형식과 크기를 확인한 뒤 다시 시도해주세요."});
    } finally {
      if (python) for (const name of ["_body", "_metadata", "_auxiliary", "_route"]) python.globals.delete(name);
    }
  }).catch(() => {});
};
