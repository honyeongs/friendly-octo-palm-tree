# 공개 테스트와 재현 방법

이 폴더에는 개인정보를 포함하지 않는 로컬 검사 결과만 보존합니다.

- [2026-10-13 로컬 테스트 보고서](2026-10-13-local.md)
- [테스트별 기계 판독 결과](2026-10-13-local.json)
- [대표 10개 시나리오 정의](../../tools/portfolio_cases.py)
- [재현용 실행기](../../tools/run_portfolio_validation.py)
- [공개 항목 제한 및 결과 집계](../../tools/validation_support.py)
- [공개 기록의 개인정보 누출 방지 회귀 검사](../../tests/test_validation_evidence.py)

## 실행

README에 안내된 Python/선택 의존성을 먼저 설치하세요. 웹 검증에는 Node.js와 Playwright/Chromium이 필요합니다.

```console
python tools/run_portfolio_validation.py --suite portfolio --output reports/portfolio.json
python tools/run_portfolio_validation.py --suite all --browser --output reports/full-validation.json
```

기존 결과 파일은 덮어쓰지 않습니다. 새 이름을 사용하세요.
전체 회귀 검사 안에도 대표 테스트가 포함되므로 두 실행의 개수를 독립 표본처럼 합산하지 않습니다.
추가 검증은 각 브라우저 스크립트 단위로 집계하며 내부 assertion 개수를 테스트 수로 부풀리지 않습니다.

## 데이터와 개인정보

개인 폴더 전체를 검색하지 않습니다. 원본 로그를 이름만 바꿔 공개하지 않습니다.
테스트별 ID·판정·소요 시간·집계·소스 지문과 검토된 고정 설명만 내보냅니다.
실제 파일 내용·원본 로그·계정명·PC 이름·IP·경로·명령줄·DB·토큰·상세 예외·스크린샷은 이 폴더에 포함하지 않습니다.
파일 검사기의 실제 파일 테스트는 이 프로젝트의 README와 소스만 복사하여 사용합니다.
로그/인증 이벤트와 공격 문자열은 실행하지 않는 합성 자료이며 실제 장비 수집 로그라고 주장하지 않습니다.

일부 테스트는 임시 인증 토큰과 암호화 키를 생성하지만 공개 보고서에는 값이 기록되지 않습니다.
외부 서비스 키를 요구하거나 실제 결제·메일·SSO 제공자에 요청하는 검증은 포함하지 않습니다.

## CI

각 push의 기존 전체 검사에 더해 Windows/Linux Python 3.11/3.14 작업에서 대표 10개를 다시 실행합니다.
새 결과는 GitHub Actions의 `public-portfolio-<OS>-<Python>` 아티팩트로 남습니다.
이 폴더의 로컬 스냅샷과 원격 CI 결과는 별개입니다. 모든 결과는 해당 실행의 범위와 환경에 한정됩니다.
로컬 PostgreSQL 검사 등 실행하지 못한 항목은 건너뜀으로 공개하고 통과로 처리하지 않습니다.

