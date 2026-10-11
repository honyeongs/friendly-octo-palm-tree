# SaaS 구조와 운영

## 모듈

`monitor`는 기존 분석 연결·인증·사건 API를 유지합니다. `saas/config.py`는 출시 설정, `identity.py`는 가입/초대/복구, `plans.py`는 한도, `billing.py`는 결제, `secrets.py`/`integrations.py`는 고객별 연결, `oidc.py`는 SSO, `network.py`는 공개 HTTPS 전송, `jobs.py`는 메일/알림, `operations.py`는 수집 상태/기한/개인정보 요청, `migration.py`는 DB 이전/복구, `detection.py`는 추가 탐지입니다. 화면도 인증·구독/운영 모듈로 나눕니다.

## 요금제 계약

- Starter: 월 이벤트 100,000, 활성 사용자 5, 활성 소스 10, 보관 30일.
- Team: 월 이벤트 1,000,000, 사용자 20, 소스 50, 보관 90일.
- Business: 월 이벤트 5,000,000, 사용자 100, 소스 100, 보관 365일.
- 체험은 Starter 한도로 14일이며 자동으로 유료 전환하지 않습니다.
- 사용량은 수신 시점 UTC 달력월 기준입니다. 동일 이벤트 재전송은 차감하지 않습니다. 충돌/한도 초과는 배치 전체와 차감을 취소합니다.
- 초대 대기 좌석도 계산합니다. 구독 만료·결제 연체 시 새 이벤트/좌석/소스는 막되 조사와 내보내기는 허용합니다. 한도 하향 시 기존 사용자를 임의 삭제하지 않습니다.
- 사용량 제한 수치는 벤치마크 결과나 처리량 보증이 아닙니다. 원래 배치 200개·1MB·상관분석 10,000개 제한은 유지됩니다.
- 보관 기간 정리는 시작/약 24시간마다 수행합니다. 요금제 하향 시 다음 정리에 이전 데이터가 삭제될 수 있으므로 고객에게 사전 안내해야 합니다.

## 결제

`mock`는 루프백 개발에서만 사용할 수 있으며 실제 청구가 없습니다. `off`는 결제를 차단합니다. `stripe`는 `NETSEC_STRIPE_KEY`, `NETSEC_STRIPE_WEBHOOK_SECRET`, `NETSEC_STRIPE_PRICES={"starter":"price_...","team":"price_...","business":"price_..."}`가 필요합니다. 키를 코드/Git에 넣지 마세요.

웹훅: `POST /api/saas/billing/webhook`. `customer.subscription.*`, `checkout.session.completed`, `checkout.session.async_payment_succeeded`를 처리합니다. 제공자 상태를 다시 조회하므로 브라우저 리다이렉트나 오래된 이벤트 상태를 신뢰하지 않습니다. 등록된 고객/서버 결제 요청/구독/가격을 대조합니다. 지원하지 않는 이벤트는 무시합니다. 서명 시각 300초·환경 일치·이벤트 ID 중복을 검사합니다.

한 조직의 진행 중 결제는 하나입니다. 불확실한 제공자 실패에서는 요청을 삭제하지 않습니다. 운영자가 기록된 request ID와 `checkout-<id>` idempotency key로 제공자 상태를 조사해야 합니다. 제공자에서 만료된 결제 요청의 자동 정리·환불 자동화는 아직 없으며 운영자가 확인해야 합니다. 실제 연체/해지/갱신과 환불은 제공자 대시보드/포털에서 확인합니다. 구독 기간은 제공자가 반환한 기간을 사용합니다. 로컬 사용량 주기와 결제 주기는 다를 수 있습니다.

## SSO

발급자는 `NETSEC_OIDC_ISSUERS`의 운영자 승인 목록에만 등록할 수 있습니다. 조직 관리자가 자신의 클라이언트 ID/비밀을 암호화 저장합니다. redirect URI는 `<NETSEC_ORIGIN>/api/saas/sso/callback`입니다. 로그인한 브라우저와 서버 저장 state를 묶고 PKCE·nonce·서명·issuer·audience·유효기간·verified email을 검사합니다. 도메인만 보고 계정을 생성하지 않고 초대/확인 완료한 활성 계정에만 연결합니다.

기본 MFA 정책은 `amr`에 `mfa` 또는 `pwd`와 `otp/hwk/swk` 조합을 요구합니다. 단일 `hwk`만으로 다중 요소를 단정하지 않습니다. 제공자 정책/클레임이 다르면 실계정으로 조정·검증해야 합니다. 필수 SSO 전환 전 관리자 자신의 성공 연결이 필요하고, 필수 전환/issuer 변경 시 기존 세션은 폐기합니다. IdP 퇴사/차단의 즉시 세션 폐기를 자동 동기화하는 SCIM/back-channel logout은 없습니다. 별도로 사용자 비활성화하고 세션을 폐기하세요.

승인 IdP의 discovery/token/JWKS endpoints는 운영자가 통제·검증해야 합니다. HTTPS 통신에 프록시 환경을 사용하지 않습니다. IdP DNS/메타데이터 변경이나 침해까지 격리하려면 네트워크 이그레스 정책을 적용하세요.

## 알림과 사건 업무

SaaS 모드에서는 기존 운영자 공통 웹훅을 사용하지 않습니다. 조직별 설정과 웹훅 호스트 허용 목록을 사용합니다. 공개 IP로만 DNS를 검증하고 그 IP로 연결하되 원래 호스트로 TLS를 검증합니다. 리디렉션/환경 프록시/사설 IP를 허용하지 않습니다. 범용 JSON 웹훅이며 Teams/Slack/Jira 전용 양식·티켓 자동 생성/양방향 동기화를 구현했다고 주장하지 않습니다. 회사 자동화 중계 서비스에 연결할 수 있습니다.

메일 수신자는 같은 조직의 이메일 확인된 활성 사용자만 허용합니다. 원본 근거·계정·IP를 외부 알림에 넣지 않습니다. 외부 전송은 at-least-once로 중복 가능하며 수신자가 delivery ID로 중복 제거해야 합니다. 기한 초과 시 최대 10회, 4시간 간격으로 재알림합니다. 재알림은 새 delivery ID를 사용하며 알림 화면의 해당 채널 상태는 최신 전송 상태입니다. 수집 지연은 운영 화면 경보로 표시됩니다. 파일 에이전트는 아직 journal 직접 구독/로그 회전 자동 추적이 아닙니다.

## PostgreSQL와 별도 처리기

`NETSEC_DATABASE_URL=postgresql://...`이면 PostgreSQL을 사용합니다. 초기 배포용 계정의 스키마 생성 권한과 운영 계정 권한 분리는 운영자가 준비해야 합니다. 데이터·쿼리는 조직 범위로 분리되지만 PostgreSQL RLS/고객별 DB는 제공하지 않습니다. DB 운영자는 모든 고객 데이터에 접근할 수 있습니다.

초기 구현은 SQLite의 원자성을 유지하기 위해 PostgreSQL 쓰기에 전역 advisory lock을 사용합니다. API/작업 처리기 여러 프로세스의 한도/중복/lease 경쟁은 직렬화되지만 고처리량/고가용성 보증은 아닙니다. 외부 조회 중 잡힌 쓰기 lock, DB connection 수, 지연, 장애 복구를 실제 부하로 검증한 뒤 조직별 lock/풀/별도 큐로 개선해야 합니다.

API에서는 `NETSEC_EMBEDDED_WORKER=0`, 별도 프로세스에서 `netsec monitor-admin --env-file .env worker`를 실행합니다. API `/healthz`는 DB 생존, `/readyz`는 최근 2분 안의 처리기 heartbeat를 확인합니다. 고객 화면에는 처리기 생존과 해당 조직의 대기량/최초 대기 시각이 표시됩니다. 컨테이너의 DB는 외부 포트를 열지 않습니다.

`deploy/compose.yaml`은 PostgreSQL/API/worker/Caddy 구성입니다. `.env`를 실제 값으로 준비하고 `docker compose --env-file .env -f deploy/compose.yaml up --build -d`로 실행합니다. DB URL의 호스트는 `database`, 비밀번호의 특수 문자는 URL 인코딩합니다. Caddy만 80/443을 공개하고 API는 지정된 게이트웨이 IP의 `X-Real-IP`만 신뢰합니다. CIDR 충돌 시 네트워크와 신뢰 IP를 함께 바꿉니다. 외부 CDN 앞에 두면 별도 신뢰 경계를 다시 검토합니다. 이미지 태그는 예시이며 출시 때 패치 버전/digest와 OS 패키지 SBOM·취약점을 별도 고정·검사해야 합니다.

## 이전·백업·복원

1. 기존 SQLite를 제공한 backup 명령으로 새 스냅샷에 복사합니다. 기존 데이터와 `.netsec-key`를 보존합니다.
2. API/worker 쓰기를 멈춘 뒤 빈 PostgreSQL에 `netsec monitor-admin --env-file .env migrate-postgres backups/snapshot.sqlite3`를 실행합니다. 기존 고객이 있는 대상에는 합치지 않습니다. 행 수·외래키/무결성 검사와 자동 증가 번호를 검증하며 실패 시 대상 트랜잭션을 롤백합니다.
3. `enable-saas` 명령으로 기존 조직에 체험 요금제를 부여합니다. 기존 계정은 즉시 강제 잠그지 않으며 SSO 전 이메일 확인이 필요합니다.
4. PostgreSQL backup은 호환되는 `pg_dump`/`pg_restore` 실행 파일이 PATH에 있어야 합니다. 비밀번호는 프로세스 인자가 아닌 자식 환경에 전달됩니다. DB와 동일하거나 더 최신의 호환 클라이언트를 사용합니다.
5. `NETSEC_RESTORE_DATABASE_URL`을 별도 빈 임시 DB로 지정하고 `restore-check backups/netsec.dump`를 실행하여 실제 복원·행 수를 확인합니다. 운영 DB는 대상이 될 수 없습니다. 임시 DB는 검증 뒤 운영자가 폐기합니다.

키를 잃으면 암호화된 연결/메일을 복구할 수 없습니다. 키는 DB와 분리 보관하되 함께 복구할 수 있도록 접근 제어합니다. 키 자동 회전/KMS/HSM 연동은 미구현입니다. 백업 암호화·접근 제어·주기·원격 보관·복원 훈련은 인프라 작업입니다.

## 개인정보 요청

관리자는 재인증 후 내보내기 또는 삭제 요청을 합니다. 내보내기는 테이블별 10,000개로 제한하고 잘린 테이블을 명시합니다. 더 큰 조직은 운영자 범위 지정 내보내기가 필요합니다. 비밀번호/세션/소스 키/연결 비밀은 제외합니다.

삭제 요청은 접수와 실행을 구분합니다. 운영자는 위탁 계약·법적 보존·외부 결제 취소를 확인한 뒤 `fulfill-delete REQUEST_ID`에서 ID를 재입력해야 합니다. 활성 Stripe 구독은 먼저 취소·상태 동기화해야 합니다. 해당 조직의 현 DB 데이터만 삭제하고 다른 고객 데이터는 보존합니다. 외부 PG·메일·백업·SDK 큐·이전 스냅샷은 자동 삭제되지 않습니다. 삭제 기록을 별도 티켓에 남기고 복원 시 삭제 요청을 재적용해야 합니다.
