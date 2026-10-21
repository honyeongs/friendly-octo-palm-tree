let worker = null;
let serial = 0;
const pending = new Map();
function runtimeStatus(text) {
  window.dispatchEvent(new CustomEvent("engine:status", {detail: text}));
}
function shutdown(error) {
  worker?.terminate(); worker = null;
  for (const task of pending.values()) { task.cleanup(); task.reject(error); }
  pending.clear();
}
function connect() {
  if (worker) return;
  runtimeStatus("분석 엔진 준비 중");
  worker = new Worker("/engine-worker.js");
  worker.onmessage = ({data}) => {
    if (data.stage) { runtimeStatus(data.stage); return; }
    const task = pending.get(data.id);
    if (!task) return;
    pending.delete(data.id); task.cleanup();
    runtimeStatus("분석 엔진 준비 완료");
    if (data.ok) task.resolve(data.result);
    else { const error = new Error(data.error || "분석하지 못했습니다."); task.reject(error); shutdown(error); }
  };
  worker.onerror = () => {
    runtimeStatus("엔진 로드 실패 · 다시 시도하세요");
    shutdown(new Error("분석 엔진을 준비하지 못했습니다. 연결 상태를 확인해주세요."));
  };
}
export async function callEngine(route, body = null, metadata = {}, signal, auxiliary = null) {
  if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
  const bytes = body instanceof Blob ? await body.arrayBuffer() : body || new ArrayBuffer(0);
  if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
  connect();
  return new Promise((resolve, reject) => {
    const id = ++serial;
    const abort = () => shutdown(new DOMException("Cancelled", "AbortError"));
    const timer = setTimeout(() => {
      runtimeStatus("처리 시간 초과");
      shutdown(new Error("처리 시간이 초과되었습니다. 더 작은 파일로 다시 시도해주세요."));
    }, 90000);
    const cleanup = () => { clearTimeout(timer); signal?.removeEventListener("abort", abort); };
    pending.set(id, {resolve, reject, cleanup});
    signal?.addEventListener("abort", abort, {once: true});
    worker.postMessage({id, route, bytes, metadata, auxiliary});
  });
}
export function forgetSession() {
  shutdown(new DOMException("Session cleared", "AbortError"));
  runtimeStatus("세션 메모리 초기화됨");
}
