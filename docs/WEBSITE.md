# NetSec Lab 웹사이트

[공개 배포·브라우저·회귀 검증 기록](WEBSITE_VERIFICATION.md)

서비스 주소: [NetSec Lab](https://netsec-lab-web.yao0422q.chatgpt.site/)

## 제공 범위

SSH·journald·PCAP 분석과 보고서 비교를 별도 Python 설치 없이 브라우저에서 실행합니다.
기존 CLI와 PC 전용 서버는 그대로 유지합니다. PC 전용 개발 서버를 인터넷에 노출하지 않습니다.
웹과 CLI는 동일한 Python 분석 모듈을 사용하며, 원본 Python 실행과 웹 결과의 일치를 테스트합니다.
NetSec 웹은 오프라인 분석 기능이며 조직 계정·서버 수집·SMTP·SSO·청구·운영 DB를 제공하는 기존 로컬 SaaS와는 별개입니다.

## Windows에서 앱으로 사용

1. Microsoft Edge 또는 Chrome에서 위 주소를 엽니다.
2. 사이트 상단의 **앱 설치**를 누르거나 주소창의 설치 아이콘을 사용합니다.
3. 설치 확인은 사용자가 직접 해야 합니다. 설치 후 시작 메뉴에서 열거나 작업 표시줄에 고정할 수 있습니다.
4. **Windows 바로가기**는 현재 사이트를 여는 `.url` 파일입니다. 별도 EXE 설치 파일이 아닙니다.
5. 설치 안내 창에서 `.ico` 아이콘도 내려받을 수 있습니다. 바탕화면 바로가기 생성·고정 선택은 브라우저/Windows 설정에 따라 다릅니다.

다운로드:
- [사이트 바로가기](https://netsec-lab-web.yao0422q.chatgpt.site/windows-shortcut.url)
- [Windows 아이콘](https://netsec-lab-web.yao0422q.chatgpt.site/icons/app.ico)
- [512px PNG](https://netsec-lab-web.yao0422q.chatgpt.site/icons/app-512.png)

PWA 설치는 사용자 동의가 필요하며 이 프로젝트가 자동으로 OS에 설치하거나 레지스트리·시작 프로그램을 변경하지 않습니다.
설치 버튼을 제공하지 않는 브라우저에서는 일반 웹사이트로 사용할 수 있습니다.

## 개인정보·보안

- 파일·로그 분석은 Web Worker의 Pyodide/CPython 메모리에서만 처리합니다.
- 파일·로그·보고서의 본문, 파일명, 계정명 등을 분석 서버로 전송하지 않습니다. 사이트 자산 GET 다운로드와 실제 파일 업로드를 구분합니다.
- 런타임 약 12 MiB는 같은 사이트에서 내려받습니다. 외부 CDN·광고·추적 스크립트는 사용하지 않습니다.
- 오프라인 캐시는 공개 앱 코드·런타임·합성 예제만 보관합니다. 사용자가 고른 파일·보고서는 CacheStorage/IndexedDB/localStorage에 저장하지 않습니다.
- 호스팅 제공자는 사이트 접속 IP·시각 등 일반 접속 정보를 처리할 수 있으므로 호스팅 계층까지 무기록이라고 주장하지 않습니다.
- 취소는 Worker를 종료합니다. 세션 지우기는 새로고침하여 이전 분석 상태를 버립니다. 브라우저/OS 자체의 물리 메모리 삭제를 보장하지는 않습니다.
- 브라우저 메모리·저장 공간 부족으로 제한 크기 이하 입력도 실패할 수 있습니다. 최초 오프라인 준비 완료 전에 연결을 끊으면 실행할 수 없습니다.
- 선택한 파일·로그 문자열은 실행하지 않습니다. Python으로 실행하는 것은 빌드에 포함된 고정 분석 모듈과 bridge뿐입니다.
- 이 정적 호스팅의 실제 HTTP 응답에는 `_headers`의 보안 헤더가 반영되지 않습니다. 주 문서 meta CSP와 Worker 응답/프레임 보호를 혼동하지 않으며, 관련 한계는 검증 기록에 공개합니다.
- 원본 보고서 내보내기는 민감정보를 포함할 수 있습니다. 공개 전 별도 비식별화가 필요합니다.
- 백신·상용 EDR·안전 인증·무결점 보증이 아닙니다.

## 구조

- `src/.../web`: 기존 분석 화면. 로컬 모드는 기존 API를 그대로 사용합니다.
- `website/bridge.py`: 허용된 분석 동작만 기존 Python 엔진에 연결합니다.
- `website/engine-worker.js`: 고정 코드 실행, 사용자 바이트·옵션은 변수로 전달합니다.
- `website/engine-client.js`: Worker 요청·취소·시간 제한·세션 관리를 담당합니다.
- `website/transport.js`: 웹 전용 메모리 분석 경로입니다. 실제 서버 POST가 아닙니다.
- `website/pwa.js`: 설치·바로가기·다른 도구 링크·세션 지우기·오프라인 상태입니다.
- `website/site.toml`: 앱 정보와 공개 주소입니다. 비밀키가 아닙니다.
- `tools/build_website.py`: 검토한 런타임 SHA-256을 확인하고 원본 분석 소스를 묶습니다.
- `website/dist`: 생성된 배포 결과이며 GitHub 소스 커밋에서 제외합니다.
- `tests/test_website.py`, `tests/browser/website.mjs`: 보안 경계·아이콘·설치 정보·브라우저/네이티브 결과·오프라인 검증입니다.

## 재현

README의 Python 및 선택 의존성 설치 방법을 먼저 적용합니다. NetSec 빌드는 `dpkt`가 필요합니다.
공식 런타임은 [Pyodide 0.29.5 배포본](https://github.com/pyodide/pyodide/releases/download/0.29.5/pyodide-core-0.29.5.tar.bz2)입니다.

```console
python tools/build_website.py --runtime-archive <pyodide-core-0.29.5.tar.bz2>
python -m unittest tests.test_website -v
npm install --no-save --package-lock=false playwright@1.64.0
npx playwright install chromium
node tests/browser/website.mjs
```

아이콘 재생성: `node tools/generate_app_icons.mjs netsec "#176b56"`.
현재 앱은 동일한 Lucide 방패 원본에 자체 앱 색상·배경을 적용했습니다.
웹 배포는 별도 Sites 소스 체크아웃에서 검증한 정적 결과와 manifest를 동기화한 뒤 저장·배포합니다.
`website/.openai/hosting.json`의 기존 project_id를 재사용해야 하며 새 Site를 중복 생성하지 않습니다.

## 라이선스

[웹 구성요소 고지](../website/THIRD_PARTY.md), 사이트의 라이선스·출처 화면과 동봉한 원본 고지를 참고하세요.
Pyodide/CPython 런타임은 수정하지 않고 별도 구성요소로 배포합니다.
자체 애플리케이션 소스에 새로운 오픈소스 라이선스를 임의로 부여하지 않았습니다.
