# 앱·서버 연결

## Python 앱

서버에 패키지를 설치하고 관리 화면에서 앱 소스를 만듭니다. 키는 환경 변수 또는 회사의 비밀 관리 도구로 전달합니다. 브라우저·모바일 앱 번들에는 수집 키를 넣지 말고 신뢰할 수 있는 백엔드에서 전송합니다.

```python
import os
from netsec.sdk import MonitorClient

monitor = MonitorClient(
    "http://127.0.0.1:8890",  # 외부 서버는 반드시 HTTPS
    os.environ["NETSEC_SOURCE_KEY"],
    outbox="data/app-outbox.sqlite3",
)
monitor.start()  # 앱 시작 시 한 번

# 기존 로그인 처리의 인증 결과가 결정된 다음 실행합니다.
# 사용자 입력 X-Forwarded-For를 그대로 믿지 말고 신뢰한 프록시에서 IP를 확정하세요.
event_id = monitor.emit(
    outcome="failure",  # 성공이면 success
    source_ip="192.0.2.10",
    username="opaque-user-123",
    host="shop-api-01",
    method="password",
)
# event_id가 None이면 로컬 큐가 가득 찼거나 쓰기 실패입니다. 운영 지표에 기록하세요.

monitor.stop()  # 앱 종료 시
```

로그인 요청에서 외부 네트워크 전송을 기다리지 않습니다. `emit()`은 최대 10,000개짜리 로컬 SQLite 큐에 저장하며 로컬 디스크 I/O는 발생합니다. 별도 스레드가 200개씩 보내고 일시 장애 시 최대 300초 간격으로 재시도합니다. 재시작해도 ID가 유지되어 서버가 중복을 제거합니다. 로컬 쓰기 권한·디스크 여유를 확인해야 하며, 마지막 종료 시 큐를 강제로 비우지 않습니다.

`status()`의 `pending`/`dead` 수를 운영 지표로 수집하세요. 키 오류·스키마 오류·배치 제한 등 영구적인 4xx는 배치 전체를 `dead`로 격리합니다. 원인을 고친 뒤 `retry_dead()`를 호출합니다. 큐 파일에는 IP와 사용자 식별자가 들어 있으므로 전용 OS 계정의 읽기/쓰기 권한을 제한합니다. 애플리케이션 종료 전 직접 `flush()`할 수도 있지만 네트워크 응답을 기다립니다.

## 다른 언어·서비스

`POST /api/v1/events`에 `Authorization: Bearer <수집 키>`와 JSON을 보냅니다. 조직·소스는 키로 결정되며 요청에서 선택할 수 없습니다.

```json
{
  "events": [{
    "event_id": "shop-login-unique-request-id",
    "timestamp": "2026-10-11T09:00:00+09:00",
    "event_type": "auth.login",
    "outcome": "failure",
    "source_ip": "192.0.2.10",
    "username": "opaque-user-123",
    "host": "shop-api-01",
    "method": "password"
  }]
}
```

예시 시각은 실행 시 현재 시각으로 바꿉니다. 타임존은 필수입니다. 202 응답의 `accepted + duplicates`가 보낸 수와 같아야 확인 완료로 취급합니다. 재전송에는 반드시 같은 `event_id`와 내용을 사용합니다. 같은 ID의 내용이 달라지면 409로 배치 전체를 취소합니다. 한 배치 최대 200개·1MB, 소스당 분당 120회, IP당 분당 600회입니다. 수집된 이벤트의 앞뒤 상관분석 구간은 최대 10,000개이며 초과하면 413으로 전체 취소합니다.

`password.change`, `role.change` 이벤트도 기록할 수 있지만 현재 자동 탐지 규칙은 `auth.login`에만 적용됩니다. OpenTelemetry의 OTLP 수신 서버는 아니며, 연동 시 위 형식으로 변환해야 합니다.

비밀번호·세션·접근 토큰·쿠키·요청 헤더를 보내지 마세요. 임의 메타데이터는 허용하지 않습니다. 이메일 대신 불투명한 사용자 식별자를 권장합니다. 인증 결과는 클라이언트의 주장이 아닌 기존 인증 시스템의 최종 결과를 보내세요.

## Linux SSH 파일 수집

SSH 소스를 만들고 키를 환경 변수로 설정합니다.

```sh
export NETSEC_SOURCE_KEY='source-key'
journalctl -u ssh -u sshd --since "30 days ago" -o json --no-pager > ssh.journal.jsonl
netsec agent ssh.journal.jsonl --format journal --endpoint http://127.0.0.1:8890
netsec agent ssh.journal.jsonl --format journal --follow --interval 5
```

파일의 정규화된 이벤트·동일 이벤트 출현 순서로 ID를 정하고 로컬 커서를 유지합니다. `--follow`는 **내보낸 파일을 주기적으로 다시 읽는 방식**이며 journal 자체를 구독하지 않습니다. 파일 작성·갱신은 운영자가 별도 구성해야 합니다. 파일 최대 20MB, 커서 보관 30일입니다. 소스를 변경할 때는 별도 `--outbox` 파일을 사용하세요. 전통적인 연도 없는 syslog는 기존과 같이 지원하지 않습니다.

기본적으로 30일보다 오래된 이벤트와 현재보다 5분 이상 미래인 이벤트를 큐에 넣지 않고 scan 통계에 표시합니다. 서버 보관 기간을 바꿨으면 에이전트의 `--max-age-days`도 맞춥니다. 부적합한 과거 기록이 새 이벤트 배치까지 막지 않도록 하는 제한이며, 시계가 맞지 않는 서버는 시간 동기화를 먼저 점검합니다.

PCAP은 기존 오프라인 분석 명령으로 처리합니다. 이번 수집 API는 패킷 파일 업로드·상시 패킷 캡처를 지원하지 않습니다.
