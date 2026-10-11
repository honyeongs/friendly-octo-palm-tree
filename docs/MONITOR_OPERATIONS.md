# NetSec Monitor 운영 가이드

## 설치·실행

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe, Linux: .venv/bin/python
python -m pip install ".[monitor]"
python run.py monitor --port 8890
```

활성화된 가상환경에서 실행하거나 해당 Python 절대 경로를 사용합니다. SQLite 외에 별도 서버·DB·외부 계정은 필요 없습니다. `.env`를 사용할 때는 `python run.py monitor --env-file .env`로 명시합니다. 환경 변수가 파일 값보다 우선합니다. 기본 DB는 실행 디렉터리의 `data/netsec.sqlite3`입니다.

기존 `analyze-ssh`, `analyze-pcap`, `serve`는 별도 동작하며 모니터 의존성을 설치하지 않아도 사용할 수 있습니다. 모든 데이터는 서버 DB가 기준이며 브라우저는 계정·사건을 저장하지 않습니다.

## 권한·인증

- 관리자: 소스 생성·폐기, 사용자 추가·역할/상태 변경, 정책·예외, 감사 기록, 사건 처리·내보내기.
- 분석가: 조직 내 사건·이벤트 조회, 담당자·상태·메모 변경, 사건 내보내기.
- 조회자: 조직 내 사건·이벤트·소스·알림 조회만 가능.

세션과 수집 키는 256비트 난수이며 DB에는 SHA-256 해시만 저장합니다. 세션은 HttpOnly·SameSite=Strict 쿠키이며 HTTPS 설정 시 Secure를 적용합니다. 변경 요청에 Origin 검사와 별도 CSRF 토큰을 요구합니다. 비밀번호는 salt가 있는 scrypt로 저장합니다. 비밀번호 변경·운영자 재설정·역할 변경·사용 중지는 관련 세션을 폐기합니다. 관리자 본인의 계정 비활성화·역할 변경은 막습니다. 사용자 삭제 대신 비활성화하여 조사 메모의 작성자를 유지합니다.

첫 조직 웹 설정은 루프백 HTTP에서만 가능하고 한 번 완료되면 잠깁니다. 추가 조직 또는 외부 배포의 첫 조직은 서버 운영자가 다음 명령으로 만듭니다. 비밀번호는 프롬프트에서 입력하며 명령 기록에 남기지 않습니다.

```sh
netsec monitor-admin --env-file .env create-org --name "Example" --email admin@example.com
netsec monitor-admin --env-file .env reset-password --org-id ORG_ID --email admin@example.com
```

조직 ID를 사용자에게 전달합니다. 이 버전에는 조직 간 접근이 가능한 웹 슈퍼 관리자는 없습니다. 서버 운영자의 OS/DB 권한은 모든 조직 데이터에 접근할 수 있으므로 별도 관리합니다.

## 탐지·조사

소스·호스트·IP 기준 반복 실패, 추가로 같은 사용자에 대한 실패 후 성공을 기존 엔진으로 분석합니다. 기본값은 60초 내 실패 5회, 마지막 실패 뒤 300초 내 성공입니다. 순서가 뒤바뀌거나 배치가 나뉘어 들어와도 저장된 앞뒤 이벤트를 조회합니다. 중첩된 반복 실패 사건은 근거를 추가하고 기존 처리 상태를 보존합니다. 동일 사건의 추가 근거마다 외부 알림을 재발송하지 않습니다. 다른 성공 이벤트는 별도 상관분석 사건이 될 수 있습니다.

사건 변경에는 version을 검사하므로 동시 수정 시 409가 반환됩니다. 상태·담당자 변경, 메모 추가, 내보내기 등을 감사 기록에 남깁니다. 정책·예외 변경은 다음 수집부터 적용하며 기존 사건을 지우거나 일괄 재분석하지 않습니다. 예외는 소스+CIDR에 적용되고 최대 30일 뒤 만료됩니다. 실패 후 성공을 침해 성공으로 단정하거나 IP를 자동 차단하지 않습니다.

## 알림

화면 알림은 항상 생성됩니다. 이메일·웹훅은 환경 설정과 조직 정책이 모두 활성화되어야 합니다. 누락 설정은 `미설정`으로 표시하며 오류가 아닙니다. 설정 후 해당 알림을 수동 재시도할 수 있습니다. 알림은 DB 큐에 저장되고 백그라운드 작업이 lease를 잡아 처리합니다. 실패 시 30초부터 지수 간격으로 최대 5회 시도합니다.

전송은 at-least-once이므로 전송 직후 프로세스가 종료되면 외부에서 중복 수신할 수 있습니다. 웹훅의 `Idempotency-Key`/`delivery_id`로 수신자가 중복 제거해야 합니다. 이메일은 Message-ID를 제공하지만 중복 방지를 보장하지 않습니다. 외부 전송에는 사건 ID·규칙·위험도·제목·로그인 필요한 링크만 넣고, 원본 근거·사용자·IP는 넣지 않습니다. 웹훅 주소는 서버 운영자만 환경 변수로 지정하며 리디렉션을 따라가지 않습니다. 현재는 모든 조직에 하나의 운영자 관리 웹훅을 공유하므로 독립 고객용 SaaS에는 조직별 비밀 저장소/수신처 분리가 추가로 필요합니다.

## 백업·보관

```sh
netsec monitor-admin --env-file .env backup backups/netsec-2026-10-11.sqlite3
netsec monitor-admin --env-file .env prune
```

SQLite backup API로 일관된 복사본을 만들고 무결성을 확인합니다. 기존 대상은 덮어쓰지 않습니다. 실행 중 DB 파일만 단순 복사하면 WAL의 최근 변경을 놓칠 수 있으므로 제공한 명령을 사용합니다. 복구는 서버를 완전히 종료한 뒤 백업을 새 경로에 복사하고 `NETSEC_DB`를 새 파일로 지정하여 재시작합니다. 기존 DB와 WAL은 덮어쓰지 말고 보존하세요. 복구된 세션·수집 키도 시점 기준으로 돌아가므로 필요하면 폐기·재발급합니다.

기본 30일 기준 정리는 서버 시작 시와 약 24시간마다 수행하고, 명령으로도 실행할 수 있습니다. 이벤트 시각·사건 마지막 관측·감사 기록 생성 시각 기준으로 삭제하며 관련 메모·알림도 함께 삭제합니다. 열린 사건도 예외 없이 해당 보관 기간을 적용합니다. 운영자가 백업 사본·SDK 큐의 보관 기간도 따로 관리해야 하며, SQLite 삭제는 물리 디스크의 안전 삭제를 보장하지 않습니다. 별도 디스크 암호화와 백업 접근 제어를 권장합니다.

## 외부 배포 전 필수 작업

1. 전용 OS 계정과 제한된 DB 디렉터리 권한, 암호화된 저장소·백업을 준비합니다.
2. 도메인과 TLS 역방향 프록시를 구성하고 `NETSEC_ORIGIN=https://실제도메인`으로 설정합니다. 프록시는 원래 Host를 보존해야 합니다. 프록시 뒤의 앱은 루프백에만 바인딩하고 방화벽으로 직접 접근을 막습니다. 기본적으로 전달 헤더는 신뢰하지 않습니다.
3. CLI에서 첫 조직을 생성한 뒤 노출합니다. HTTPS 모드의 웹 초기 설정은 차단됩니다.
4. 헬스 체크 `/healthz`, 프로세스 재시작, 디스크 용량·큐 적체·백업 복구를 감시합니다. 프록시의 요청 크기·속도 제한도 설정합니다.
5. 필요한 SMTP/범용 웹훅 설정을 넣고 실제 수신을 검증합니다. `.env`를 Git에 올리지 않습니다.
6. 회사의 보관·개인정보·사고 대응 정책에 맞게 검토하고 독립 보안 검토를 받습니다.

이 버전은 단일 인스턴스 SQLite 기반 제한된 시범 운영용입니다. PostgreSQL, 여러 서버 분산 처리, SSO/MFA, 이메일 소유 확인, 원본 로그 위변조 방지, 외부 SIEM/OTLP 수신, 고가용성과 규제 준수 인증은 제공하지 않습니다. 인터넷 공개용 인증 서비스나 상용 보안 제품으로 검증되었다고 간주하지 않습니다.

## 모듈·검사

화면의 사건·이벤트·알림·감사 목록은 페이지당 50개입니다. 사건 JSON 내보내기는 최신 1,000개까지이며 초과하면 `truncated: true`를 표시합니다. 상관분석 근거는 화면에서 200개까지 표시하지만 상세 API와 사건 내보내기에는 저장된 근거가 포함됩니다.

`monitor/config.py` 설정, `schema.sql`/`database.py` 저장, `security.py`/`dependencies.py` 인증·권한, `ingestion.py` 수집, `detection.py` 기존 엔진 연결, `routes_*` API, `notifications.py` 알림, `maintenance.py` 백업·보관, `ui` 화면, `sdk.py` 앱 모듈, `monitor/agent.py` 파일 수집, `demo` 샘플 앱으로 나눴습니다.

```sh
python -m pip install ".[packets,monitor,test]"
python -m unittest discover -s tests -t . -v
node --test tests/web/*.test.mjs
node tests/browser/monitor.mjs
```

브라우저 검사는 Playwright와 Chromium이 필요하며 기존 보고서 화면 검사는 `tests/browser/smoke.mjs`입니다. 스크린샷·테스트 DB·실행 데이터는 Git에서 제외합니다. 관리자 로그인 후 `/api/openapi`에서 API 명세를 확인할 수 있습니다.

참고 기준: [FastAPI 모듈화](https://fastapi.tiangolo.com/tutorial/bigger-applications/), [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [OWASP 비밀번호 저장](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). scrypt 설정은 N=32768, r=8, p=3이며 자동 보안 인증을 의미하지 않습니다.
