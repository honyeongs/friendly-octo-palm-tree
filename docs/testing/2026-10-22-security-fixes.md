# 로컬 공개 테스트 기록

- 저장소: `friendly-octo-palm-tree`
- 실행 시각(UTC): `2026-10-22T00:18:19.989593+00:00`
- 환경: Windows / Python 3.14.7
- 검사 당시 기준 커밋: `519375a2e0e867038da280d67165c74f83118154`
- 보고서는 아직 커밋되지 않은 테스트 실행기 변경을 포함한 작업 트리를 검사한 결과입니다.
- 검사 대상 파일 140개의 정규화 SHA-256: `de033cc7e383ff44f81aea3a8bb257803b87dc2ee931a1bd725a70d034ef9dca`
- 위 값은 소스 지문이며 개인 파일 해시나 디지털 서명이 아닙니다.

## 대표 시나리오 10개

기존 테스트 중 서로 다른 기능 10개를 선정하여 별도 재실행했습니다. 전체 회귀 검사와 중복되므로 독립 표본 20개로 합산하지 않습니다.

- **P01: SSH CLI sample and independent expected summary**
  결과: `passed`, 419.863 ms. 재현 대상: `tests.test_cli.CliTests.test_sample_matches_independent_expected_summary`.
- **P02: Native journal microsecond timestamp**
  결과: `passed`, 0.119 ms. 재현 대상: `tests.test_journal.JournalTests.test_native_microseconds_preserved`.
- **P03: Failure burst followed by matching success**
  결과: `passed`, 0.13 ms. 재현 대상: `tests.test_success_after_failures.SuccessCorrelationTests.test_matching_user_and_burst`.
- **P04: PCAP and PCAPNG transport parity**
  결과: `passed`, 99.635 ms. 재현 대상: `tests.test_packets.PacketTests.test_pcap_and_pcapng_have_same_transport_counts`.
- **P05: Event ingestion and idempotent deduplication**
  결과: `passed`, 994.593 ms. 재현 대상: `tests.test_monitor.MonitorTests.test_ingestion_detects_and_deduplicates`.
- **P06: Tenant isolation for reads and mutations**
  결과: `passed`, 1527.901 ms. 재현 대상: `tests.test_monitor.MonitorTests.test_isolation_lists_details_mutations_and_assignees`.
- **P07: CSRF token and Origin enforcement**
  결과: `passed`, 901.569 ms. 재현 대상: `tests.test_monitor.MonitorTests.test_csrf_and_origin`.
- **P08: Atomic SaaS quota, replay and conflict**
  결과: `passed`, 1151.969 ms. 재현 대상: `tests.test_saas.SaasTests.test_quota_atomic_replay_and_conflict`.
- **P09: Encrypted tenant-bound integration secrets**
  결과: `passed`, 1218.148 ms. 재현 대상: `tests.test_saas.SaasTests.test_integrations_encrypt_bound_secrets_and_redact`.
- **P10: OIDC signature, issuer, audience, expiry and nonce**
  결과: `passed`, 309.075 ms. 재현 대상: `tests.test_oidc_crypto.OidcCryptoTests.test_signature_issuer_audience_expiration_nonce`.

## 전체 자동 테스트

실행 178개: 통과 154, 실패 0, 오류 0, 건너뜀 24, fixture 오류 0.
전체 테스트별 결과와 소요 시간은 같은 폴더의 JSON에 기록했습니다.
- 건너뜀 사유 코드 `other_not_published`: 1개.
- 건너뜀 사유 코드 `postgres_not_configured`: 23개.

## 웹 검증

이번 실행에는 웹 검증을 포함하지 않았습니다.

## 공개 정보 범위

개인 폴더를 임의로 탐색하지 않았습니다. 테스트 코드가 지정한 프로젝트 파일과 격리된 임시 테스트 자료만 사용했습니다.
로그·계정·호스트·IP·명령줄·DB·세션/소스 토큰·예외 상세·절대 경로·브라우저 화면은 공개 보고서에서 제외했습니다.
기존 샘플의 이름은 가상 식별자이며 실제 개인정보를 단순 가명 처리한 자료가 아닙니다.
임시 DB 비밀번호·암호화 키·인증 토큰은 테스트 실행 중 생성되거나 코드의 명시적 테스트용 값이며 보고서로 내보내지 않습니다.

## 한계

- Local authentication/tenant tests use isolated temporary SQLite databases and synthetic events.
- Packet inputs are repository lab fixtures; this run does not capture the user's network.
- PostgreSQL contracts are skipped locally unless --allow-postgres explicitly targets a dedicated test server.
- Real SMTP, SSO providers, payment charging, Docker and a live Linux SSH lab are not exercised by this local run.
- 성공은 해당 테스트의 기대 동작 일치이며 안전 인증·무결점·법적 적합성 보증이 아닙니다.
- 소요 시간은 이 PC의 단일 실행 관측값이며 성능 벤치마크가 아닙니다.
- 이 문서의 로컬 결과와 GitHub Actions의 원격 결과는 별개입니다.

## 재현

```console
python tools/run_portfolio_validation.py --suite all --browser --output reports/local-validation.json
```

Python 및 선택 의존성과 Playwright/Chromium 설치 방법은 README를 참고하세요.
대표 10개만 실행: `python tools/run_portfolio_validation.py --suite portfolio`.
개별 시나리오는 위 테스트 ID를 `python -m unittest <test_id> -v`로 실행할 수 있습니다.
PostgreSQL은 기본적으로 실행하지 않습니다. 운영 DB가 아닌 별도 테스트 DB에만 명시적으로 허용하세요.
