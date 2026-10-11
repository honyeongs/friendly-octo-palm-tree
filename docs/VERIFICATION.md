# 검증 기록

검증일: 2026-10-11 (Asia/Seoul)

## 0.2 확장 검증

사용자가 Linux 로그 지원·실습, 실패 후 인증 성공 상관분석, 패킷 연계, 결과 비교 화면 전체 구현과 기존 GitHub 저장소 업로드를 승인했다.

- Windows Python 3.14.7: 확장 포함 Python 테스트 70개 통과.
- Node.js: 보고서 검증·비교·시간대·파일 크기 제한 테스트 8개 통과.
- 실제 Chromium: 예제 로드, 검색, 근거 선택, 네 가지 보기, 시간대 전환, 구버전 1.0 JSON 가져오기, 잘못된 JSON 거부, HTML 문자열의 안전한 표시, 내보내기, 예제 복원 확인.
- 화면 크기: 데스크톱 1440px, 모바일 390px/360px에서 페이지 가로 넘침과 버튼 글자 넘침 검사. 스크린샷 육안 확인 후 모바일 시간대 선택 글자 표시를 수정.
- 합성 통합 예제: SSH 실패 14개·성공 2개, 반복 실패 구간 2개, 같은 사용자 실패 후 성공 1개. 패킷 14개 중 SYN 7개, 연결 시도 6개, SYN 재전송 1개, SYN-ACK 6개, RST 1개. IPv4 탐지 구간에는 연결 시도 5개의 패킷 근거가 연결되며 IPv6 구간에는 대응 캡처가 없어 matched=false이다.
- PCAP와 PCAPNG, RAW IPv6와 Linux cooked v1/v2, 잘못된 캡처와 다중 호스트 매핑을 검사.
- 실제 Linux SSH 실습과 원격 CI 상태는 아래 원격 검증 기록에 별도로 남긴다. 로컬 Windows에서 이를 통과했다고 주장하지 않는다.

## 원격 검증 기록

구현은 기존 GitHub main에 업로드했다. 기능 코드 커밋은 `b2a9407976610088dd58eb69873c2661c5442fb9`이며 [원격 검사 38100969246](https://github.com/honyeongs/friendly-octo-palm-tree/actions/runs/38100969246)의 최종 결과는 **success**이다.

- Windows/Linux × Python 3.11/3.14의 네 가지 테스트 작업 모두 통과.
- 원격 Chromium 데스크톱·모바일 및 웹 데이터 테스트 통과.
- 실제 Linux 실습 통과: 인증 실패 5회, 성공 1회, 반복 실패 구간 1개, 실패 후 성공 상관분석 1개, 실제 캡처 패킷 151개. 스크립트가 TCP 시도 6회 이상과 SSH 탐지 구간의 패킷 근거 연결을 함께 검증했다.
- 환경: Ubuntu 24.04.5, Python 3.14.8, OpenSSH_9.6p1 Ubuntu-3ubuntu13.19.
- 최초 실습에서는 정상 공개키 인증이 거부됐다. 일회성 sshd에 PAM 계정 검사를 활성화한 뒤 실패 5회·정상 성공 1회가 재현되었으며 재검사가 통과했다. 운영 SSH 설정이나 계정 정보는 변경하지 않았다.
- 실제 원본 journal·PCAP·개인키는 Git 저장소와 Actions 아티팩트에 넣지 않았다. 사례 요약, 분석 보고서와 캡처 통계 로그만 아티팩트로 보관한다.

재현 조건과 해석은 CASE_STUDY.md에 정리했다. 위 실행은 기능 코드에 대한 검증 기록이며, 이 문서 자체를 추가하는 후속 커밋의 검사 상태는 GitHub의 최신 main 실행에서 확인할 수 있다.

## 아래는 초기 0.1 검증 이력

## 환경

- Windows, Python 3.14.7
- 원본 저장소의 main / 5acc790에서 로컬 복제 후 구현
- 프로젝트 소스: outputs/friendly-octo-palm-tree
- 검증 환경은 프로젝트 바깥 작업 폴더의 전용 가상환경에 구성

## 설치 검증

전용 가상환경에서 `python -m pip install .`로 wheel 빌드와 설치가 성공했다. 패키지 버전은 netsec-ssh-analyzer 0.1.0이며 실행 의존성은 없다. `python -m pip check`는 `No broken requirements found`를 반환했다.

로컬 샌드박스의 임시 폴더 권한 제한 때문에 가상환경 생성·설치·임시 파일을 사용하는 테스트는 승인된 일반 실행 환경에서 수행했다. 프로젝트 코드와 테스트 자체의 변경으로 이 환경 제한을 우회하지 않았다.

## 자동 테스트

설치한 패키지를 사용하는 가상환경에서 다음 검사를 수행했다.

```console
python -m unittest discover -s tests -t . -v
```

결과: **41개 테스트 통과, 실패 0개, 건너뜀 0개**.

검사 범위는 SSH 파싱, UTC/IP 정규화, 정확히 60초 및 60초 초과 경계, IP/호스트 분리, 성공 이벤트 제외, 순서가 뒤섞인 입력, 병합 근거 중복 방지, 10,000개 동시 실패, 100개 재현 가능한 난수 사례와 독립 윈도 계산 비교, CLI 입출력, 인코딩, 입력 덮어쓰기 및 하드 링크 보호, 기존 결과 파일 보호, 설치된 모듈 진입점이다.

## 실제 명령 실행

설치된 콘솔 명령:

```console
netsec analyze-ssh samples/ssh/demo.log --output samples/ssh/demo-report.json
```

결과: 종료 코드 0, 인증 이벤트 16개(실패 14·성공 2), 의심 구간 2개, 관련 없는 줄 1개, 손상된 줄 1개. 18번 줄의 잘못된 IP는 경고와 결과 통계에 기록된다. 생성된 JSON은 samples/ssh/demo-report.json에 보관했다.

설치 없는 소스 실행:

```console
python run.py analyze-ssh samples/ssh/normal.log
```

결과: 종료 코드 0, 인증 이벤트 6개(실패 4·성공 2), 의심 구간 0개. 출력 JSON과 실행 요약을 확인했다.

## GitHub Actions와 공개 상태

.github/workflows/tests.yml에 Windows/Linux × Python 3.11/3.14의 네 가지 조합을 구성했다. 패키지 설치, 테스트, 설치된 콘솔 명령으로 데모 분석, 보고서 아티팩트 저장을 수행하는 설정이다.

이번 작업에서는 원격 커밋·push·PR 생성 및 원격 GitHub Actions 실행을 수행하지 않았다. 따라서 Linux와 Python 3.11, 원격 CI 통과는 아직 검증하지 않았다. 로컬 구현 결과와 원격 저장소 상태를 구분해야 한다.

실제 Linux SSH 서버, 실시간 수집, 패킷 캡처, 웹 화면도 이번 승인 범위에 포함되지 않아 검증하지 않았다. 다음 단계는 EXTENSION_IDEAS.md의 실제 Linux 로그 검증이다.
