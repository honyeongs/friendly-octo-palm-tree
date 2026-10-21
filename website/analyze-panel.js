import {callEngine} from "./engine-client.js";
const form = document.querySelector("#raw-form");
let controller = null;
let generation = 0;
function status(text) { document.querySelector("#raw-status").textContent = text; }
function busy(value) {
  document.querySelector("#raw-analyze").disabled = value;
  document.querySelector("#raw-example").disabled = value;
  document.querySelector("#raw-cancel").hidden = !value;
}
form.addEventListener("submit", async event => {
  event.preventDefault();
  if (controller) return;
  const log = document.querySelector("#raw-log").files[0];
  const capture = document.querySelector("#raw-pcap").files[0];
  if (!log) {status("분석할 로그를 선택해주세요."); return;}
  if (log.size > 8 * 1024 * 1024 || (capture && capture.size > 8 * 1024 * 1024)) {
    status("로그와 PCAP은 각각 8 MiB 이하여야 합니다."); return;
  }
  const epoch = ++generation;
  const active = new AbortController(); controller = active;
  busy(true);
  status("분석 중");
  try {
    const data = await callEngine("/api/ssh", log, {
      name: log.name, capture_name: capture?.name, format: document.querySelector("#raw-format").value,
      window: Number(document.querySelector("#raw-window").value),
      threshold: Number(document.querySelector("#raw-threshold").value), success: 300,
      server_ip: capture ? document.querySelector("#raw-ip").value.trim() : "",
      server_host: capture ? document.querySelector("#raw-host").value.trim() : "",
    }, active.signal, capture ? await capture.arrayBuffer() : null);
    if (epoch !== generation) return;
    if (data.status !== 200) throw new Error(data.data.error);
    document.dispatchEvent(new CustomEvent("netsec:report", {detail: data.data}));
    status("분석 완료 · 보고서 B");
  } catch (error) {
    if (epoch === generation) status(error.name === "AbortError" ? "분석 취소됨" : error.message);
  } finally {
    if (epoch === generation) {
      controller = null;
      busy(false);
    }
  }
});
document.querySelector("#raw-cancel").onclick = () => controller?.abort();
document.querySelector("#raw-example").onclick = async () => {
  controller?.abort();
  const epoch = ++generation;
  const active = new AbortController(); controller = active;
  document.querySelector("#raw-log").value = "";
  busy(true); status("합성 로그 준비 중");
  try {
    const response = await fetch("/samples/demo.log", {signal: active.signal});
    if (!response.ok) throw new Error();
    const body = await response.blob();
    if (epoch !== generation) return;
    const transfer = new DataTransfer();
    transfer.items.add(new File([body], "synthetic-ssh.log"));
    document.querySelector("#raw-log").files = transfer.files;
    document.querySelector("#raw-pcap").value = "";
    status("합성 로그 선택됨");
  } catch (error) {
    if (epoch === generation) status(error.name === "AbortError" ? "예제 준비 취소됨" : "예제를 불러오지 못했습니다.");
  } finally {
    if (epoch === generation) { controller = null; busy(false); }
  }
};
for (const id of ["raw-log", "raw-pcap"]) document.querySelector("#" + id).addEventListener("change", () => {
  generation++; controller?.abort(); controller = null;
  busy(false); status("파일 선택됨");
});
document.querySelector("#reset").addEventListener("click", () => {
  generation++; controller?.abort(); controller = null;
  form.reset(); status("로그 선택 대기");
  busy(false);
});
