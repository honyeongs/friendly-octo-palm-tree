# SaaS 검증 기록

추가 수정: [SSO 취소 경합·오류 응답·공개 웹 보안 헤더 수정과 재검증](SECURITY_FIXES_2026-10-22.md).

후속 조치: [2026-10-22 certifi 보안 업데이트와 재검증](SECURITY_UPDATE_2026-10-22.md). 아래 결과는 원래 검토일의 기록으로 유지합니다.

검토일: 2026-10-11. 아래 결과는 실제 실행을 확인한 기록입니다.

## 로컬 검증

- Python 3.14 전체 unittest: 146개, 실패 0, 통과 127, 건너뜀 19. PostgreSQL 전용 18개와 Windows 샌드박스의 하드링크 1개는 이 로컬 실행에서 검증되지 않았습니다. PostgreSQL은 아래 별도 CI에서 실행했습니다.
- Node 보고서 검증/비교: 8개 통과.
- Playwright 기존 비교 화면: 예제/검색/시간대/4개 보기/이전 보고서/오류/이스케이프/내보내기/모바일 통과.
- Playwright 모니터: 초기 설정/수집 키/이벤트/사건 처리/내보내기/샘플 앱/재시작/뷰어/모바일 통과.
- Playwright SaaS: 가입/로컬 이메일 확인/로그인/체험/청구 없는 테스트 구독/초대/탐지/처리 기한/수집 상태/암호화 설정/조직 내보내기/360 및 390px 모바일 통과.
- pip-audit: 잠금 파일 런타임 31개, 알려진 취약점 0개.
- Bandit: 전체 19개 경고를 검토했고 high 0개. 상세 해석과 잔여 위험은 `SECURITY_REVIEW.md`에 기록합니다.
- 0.4.0 wheel 빌드와 SaaS 스키마/UI/아이콘 고지 포함 확인 통과. 런타임 31개 패키지의 고지 35개 파일 SHA-256이 목록과 일치했습니다. PowerShell 실행기 구문 검사도 통과했습니다.
- 별도 로컬 SaaS 미리보기는 8892에서 `/healthz=ok`, `/readyz=ready`를 확인했습니다. 기존 8890 DB는 바꾸지 않았습니다. 실행기 최초 설치 전체 과정을 새 PC에서 검증한 것은 아닙니다.

## CI와 외부 검증 구분

[최종 코드 7135b37의 CI 실행](https://github.com/honyeongs/friendly-octo-palm-tree/actions/runs/38148923071)은 9개 작업이 모두 성공했습니다.

- Windows/Ubuntu Python 3.11/3.14 전체 테스트 및 설치 CLI 분석.
- 실제 Linux 루프백 SSH·native journal·패킷 실험.
- 보고서 비교/운영 앱/SaaS의 3종 브라우저 흐름과 모바일 화면.
- 실제 PostgreSQL 17 계약 17개와 SQLite 이전/pg_dump/별도 DB 복원 1개, 총 18개.
- 의존성 감사와 정적 분석 게이트, 전체 경고 아티팩트 보존.
- non-root 컨테이너 빌드/패키지 확인, Compose 구성과 Caddy TLS 설정 검증.

이 문서의 결과 기록 후속 커밋은 문서만 변경하며, 실행 검증 대상 코드 SHA는 위와 같습니다.

[8c09a3c 실행](https://github.com/honyeongs/friendly-octo-palm-tree/actions/runs/38148633785)에서 실제 PostgreSQL 17의 조직/한도/권한/복구 18개 테스트가 통과했습니다. 최초 실패는 Ubuntu 기본 저장소에 client 17이 없어 발생했으며 공식 서명 PGDG 저장소로 설치해 해결했습니다. 컨테이너 non-root 빌드/패키지 확인, Linux SSH/패킷 실험과 3종 브라우저도 해당 실행에서 통과했습니다. 이후 부분 백업 실패 정리와 Compose/Caddy 설정 검사를 추가했습니다.

실제 공개 서버 배포·TLS 발급·외부 SMTP·기업 IdP·실결제·독립 침투 테스트·법률 자문은 수행하지 않았습니다. 소스 업로드, CI 성공, 실제 판매 운영은 서로 다른 단계입니다. `SAAS_START_HERE.md`에 사용자가 준비할 항목을 정리했습니다.
