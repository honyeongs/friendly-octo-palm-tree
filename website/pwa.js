import {callEngine, forgetSession} from "./engine-client.js";
const config = await fetch("/site-config.json").then(r => r.json());
let installEvent = null;
const strip = document.createElement("section");
strip.className = "site-strip";
strip.setAttribute("aria-label", "웹 앱");
strip.innerHTML = `<div class="device-state"><img src="/assets/shield-check.svg" alt=""><span>내 기기에서 처리</span><span id="engine-state" role="status">엔진 준비 대기</span></div><div class="site-actions"><details class="other-tools"><summary>다른 도구</summary><nav id="other-tools" aria-label="다른 도구"></nav></details><button id="install-app" type="button"><img src="/assets/download.svg" alt="">앱 설치</button><a id="windows-shortcut" href="/windows-shortcut.url" download title="Windows 바로가기 다운로드" aria-label="Windows 바로가기 다운로드"><img src="/assets/download.svg" alt=""><span class="desktop-label">Windows 바로가기</span><span class="mobile-label">바로가기</span></a><button id="session-clear" type="button" title="파일·로그 세션 지우기" aria-label="파일·로그 세션 지우기"><img src="/assets/rotate-ccw.svg" alt=""></button></div>`;
document.querySelector("body > header").after(strip);
for (const tool of config.tools) {
  const link = document.createElement("a");
  link.href = tool.url; link.textContent = tool.title;
  if (tool.id === config.id) link.setAttribute("aria-current", "page");
  document.querySelector("#other-tools").append(link);
}
const dialog = document.createElement("dialog");
dialog.className = "install-dialog";
dialog.innerHTML = `<div class="dialog-heading"><h2>Windows 앱 설치</h2><button type="button" id="close-install" aria-label="설치 창 닫기">×</button></div><img class="app-icon-preview" src="/icons/app-192.png" alt=""><p id="install-description"></p><ol><li>Microsoft Edge 또는 Chrome에서 이 사이트를 엽니다.</li><li>주소창의 앱 설치 버튼이나 브라우저 메뉴의 ‘앱 설치’를 선택합니다.</li><li>설치 후 시작 메뉴에서 열거나 작업 표시줄에 고정할 수 있습니다.</li></ol><div class="install-links"><a href="/windows-shortcut.url" download>Windows 바로가기 (.url)</a><a href="/icons/app.ico" download>앱 아이콘 (.ico)</a></div><p class="small-print">별도 EXE·관리자 권한이 필요하지 않습니다. 첫 준비 후 앱 자산만 오프라인 보관하며, 선택한 파일·로그와 보고서는 저장하지 않습니다.</p>`;
document.body.append(dialog);
document.querySelector("#install-description").textContent = config.title;
document.querySelector("#close-install").onclick = () => dialog.close();
dialog.addEventListener("click", event => {if (event.target === dialog) dialog.close();});
window.addEventListener("beforeinstallprompt", event => {
  event.preventDefault(); installEvent = event;
  document.querySelector("#install-app").dataset.ready = "true";
});
document.querySelector("#install-app").onclick = async () => {
  if (installEvent) {
    const event = installEvent; installEvent = null;
    await event.prompt(); await event.userChoice;
  } else dialog.showModal();
};
window.addEventListener("appinstalled", () => {
  document.querySelector("#install-app").textContent = "설치됨"; installEvent = null;
});
window.addEventListener("engine:status", event => {
  document.querySelector("#engine-state").textContent = event.detail;
});
document.querySelector("#session-clear").onclick = () => {
  forgetSession();
  location.replace(location.pathname);
};
const localLabel = document.querySelector(".local");
if (localLabel) localLabel.textContent = "BROWSER LOCAL";
const footer = document.createElement("footer");
footer.className = "site-footer";
footer.innerHTML = `<span>파일·로그는 브라우저 메모리에서 분석 · 자동 업로드·보관 없음</span><a href="/privacy.html">개인정보</a><a href="/licenses.html">라이선스·출처</a><a id="source-link">GitHub</a><span id="offline-state">온라인</span>`;
document.body.append(footer);
document.querySelector("#source-link").href = config.repository;
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready).then(() => {
    document.querySelector("#offline-state").textContent = "오프라인 준비 완료";
  }).catch(() => { document.querySelector("#offline-state").textContent = "오프라인 보관 불가"; });
}
window.addEventListener("offline", () => {document.querySelector("#offline-state").textContent = "오프라인";});
if (config.id === "inspector") {
  const button = document.createElement("button");
  button.type = "button"; button.className = "example-button"; button.textContent = "합성 ZIP 예제";
  button.onclick = async () => {
    try {
      const response = await fetch("/samples/example.zip");
      if (!response.ok) throw new Error();
      document.dispatchEvent(new CustomEvent("inspector:sample", {detail: new File([await response.blob()], "synthetic-example.zip")}));
    } catch { document.querySelector("#message").textContent = "예제를 불러오지 못했습니다."; }
  };
  document.querySelector(".section-heading").append(button);
  callEngine("/api/health").catch(() => {document.querySelector("#engine-state").textContent = "엔진 준비 실패 · 검사 시 다시 시도";});
}
