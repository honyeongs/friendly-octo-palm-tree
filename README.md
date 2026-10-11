# friendly-octo-palm-tree
친근한 문어야자나무?

## SSH 인증 로그 분석 도구

OpenSSH 텍스트 및 Linux journald JSON에서 반복 인증 실패와 실패 후 성공한 인증을 분석하는 네트워크·보안 포트폴리오 프로젝트입니다. 선택적으로 PCAP/PCAPNG의 TCP 관측을 연결하고, 웹 화면에서 두 결과를 비교합니다. Python 3.11 이상을 지원합니다. 기본 로그 분석과 비교 화면은 외부 Python 패키지 없이 실행되며, 패킷 분석에는 dpkt가 필요합니다.

프로젝트의 범위와 완료 기준은 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)에 정리했습니다.

## 바로 실행

터미널을 이 README가 있는 프로젝트 폴더에서 열고 실행합니다. 패키지 설치 없이 동작합니다.

```console
python run.py analyze-ssh samples/ssh/demo.log --output report.json
```

합성 데모의 기대 결과는 의심 구간 2개입니다. IPv4에서 40초 동안 실패 5회, IPv6에서 정확히 60초 동안 실패 5회를 탐지합니다. 다른 IP의 실패 4회는 탐지하지 않습니다. 의도적으로 손상시킨 18번 줄은 경고와 통계에 남깁니다.

```console
python run.py analyze-ssh samples/ssh/normal.log
python run.py analyze-ssh samples/ssh/demo.log --window-seconds 60 --threshold 5
python run.py --help
```

`--output`을 생략하거나 `-`로 지정하면 JSON을 표준 출력에, 실행 요약과 경고는 표준 오류에 출력합니다. 기존 결과 파일을 바꾸려면 `--overwrite`를 명시합니다. 입력 로그 자체는 덮어쓸 수 없습니다. 출력 폴더는 미리 존재해야 합니다.

## Linux 로그와 인증 상관분석

실제 Linux에서 `journalctl -u ssh -u sshd -o json --no-pager > ssh.journal.jsonl`로 내보낸 파일을 읽습니다. 시스템에 따라 서비스 이름은 ssh.service 또는 sshd.service입니다. 시간은 __REALTIME_TIMESTAMP에서 UTC로 정규화하고, 연도나 시간대를 추측하지 않습니다.

```console
python run.py analyze-ssh samples/ssh/journal.jsonl --format journal --output journal-report.json
python run.py analyze-ssh samples/ssh/correlated.log --success-window-seconds 300
```

기본 상관분석은 같은 호스트·IP·사용자에 대해 60초 안에 실패 5회 이상이 있었고, 그 마지막 실패 뒤 300초 이내에 성공한 첫 인증을 찾습니다. 성공 이벤트를 경계로 실패 이력을 초기화합니다. 실패 직후 성공한 인증은 검토할 근거이며 침해 성공을 단정하지 않습니다.

실제 SSH 서버와 네이티브 journal, tcpdump를 함께 검증하는 [Linux 실습 실행기](labs/ssh/README.md)를 제공합니다.

## 패킷 분석과 로그 연결

패킷 기능을 사용할 환경에 선택 의존성을 설치합니다.

```console
python -m pip install ".[packets]"
netsec analyze-pcap samples/packets/demo.pcapng --server-ip 192.0.2.100
netsec analyze-ssh samples/ssh/journal.jsonl --pcap samples/packets/demo.pcap --server-ip 192.0.2.100 --output combined-report.json
```

SYN, SYN-ACK, RST와 초기 순서 번호 기반 SYN 재전송을 집계합니다. 시간 범위와 출발지 IP가 맞는 패킷을 각 SSH 탐지 구간에 연결합니다. 로그에 여러 호스트가 있으면 `--server-host`로 캡처와 대응하는 호스트를 지정해야 합니다. `--server-port`의 기본값은 22이며, `--packet-margin-seconds`의 기본값은 5입니다.

단일 인터페이스 PCAP/PCAPNG를 지원하며, Ethernet, RAW IP, Linux cooked, loopback 링크 형식을 읽습니다. 여러 section/interface의 PCAPNG와 시각 없는 패킷 블록은 명시적으로 거부합니다. 암호화된 SSH 패킷에서 사용자나 인증 결과를 알아내지는 않습니다.

## 결과 비교 화면

```console
python run.py serve --port 8765
```

[로컬 화면](http://127.0.0.1:8765)에서 보고서 A/B에 JSON을 열면 요약 차이, 탐지 구간, 인증 상관분석, TCP 관측과 근거를 확인할 수 있습니다. IP·호스트·사용자 검색, UTC/한국 시간 전환, JSON 내보내기와 예제 복원을 제공합니다. 보고서 파일은 브라우저에서 읽으며 서버로 전송하지 않습니다. 구버전 schema 1.0 및 현재 1.1을 지원합니다.

화면은 패키지에 포함되어 설치 후 `netsec serve`로도 실행할 수 있습니다. 외부 CDN이나 별도 웹 빌드는 필요하지 않습니다. 첫 화면은 합성 예제이며 실제 침해 사례가 아닙니다.

## 설치해서 사용

빌드 도구를 내려받을 때는 네트워크가 필요할 수 있습니다. 실행에 필요한 별도 서비스, 계정, 키는 없습니다.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\netsec.exe analyze-ssh samples/ssh/demo.log --output report.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/netsec analyze-ssh samples/ssh/demo.log --output report.json
.venv/bin/python -m unittest discover -s tests -t . -v
```

설치 후 `python -m netsec analyze-ssh ...` 형식도 지원합니다. 설치한 소스 코드를 수정한 뒤에는 다시 설치해야 변경 내용이 반영됩니다.

## 입력과 결과

지원하는 로그의 예시는 다음과 같습니다. UTF-8 파일을 사용하고 ISO 8601 시각에 `Z` 또는 UTC 오프셋을 명시합니다.

```text
2026-10-11T09:01:00+09:00 lab sshd[102]: Failed password for invalid user admin from 192.0.2.10 port 50001 ssh2
```

- `password`, `publickey`, `keyboard-interactive/pam`의 실패와 성공을 읽습니다.
- 기본 탐지 기준은 60초 이내 실패 5회입니다. 시간 구간은 양 끝을 포함합니다.
- 시간은 UTC로 정규화하며 로그 순서가 뒤섞여 있어도 분석합니다.
- 겹친 탐지 구간은 병합하고, 전체 실패 수와 이동 구간 최대 실패 수를 따로 표시합니다.
- 지원 이벤트가 없으면 종료 코드 2를 반환합니다. 의심 구간을 발견한 정상 실행은 종료 코드 0입니다.

연도·시간대가 없는 전통적 syslog와 실시간 수집은 현재 지원하지 않습니다. 자세한 의미와 한계는 [탐지 규칙](docs/detection-rules.md)을 참고합니다.

샘플은 모두 합성 데이터이며 실제 공격·침해 사례가 아닙니다. [기대 요약](samples/ssh/expected-summary.json)과 [데모 JSON 보고서](samples/ssh/demo-report.json)를 비교할 수 있습니다.

## 구조와 자동 검사

`src/netsec` 아래에서 `parsers`는 입력 해석, `detectors`는 탐지·인증 상관분석, `packets`는 전송 계층 관측, `reporters`는 결과 저장, `web`은 결과 비교를 담당합니다. `analysis.py`가 분석 흐름을 연결하고 `cli.py`는 명령 처리를 담당합니다.

```console
python -m unittest discover -s tests -t . -v
node --test tests/web/*.test.mjs
python scripts/make_samples.py
```

전체 Python 테스트와 샘플 재생성에는 패킷 옵션 설치가 필요합니다. Node.js 22 이상은 웹 데이터 테스트에 사용합니다. 브라우저 검증은 `npm install --no-save --package-lock=false playwright@1.64.0`, `npx playwright install chromium`, `npm run test:browser`로 실행합니다. 개발용 패키지·브라우저 설치에는 네트워크가 필요합니다.

[GitHub Actions 설정](.github/workflows/tests.yml)은 Windows/Linux와 Python 3.11/3.14 테스트, 실제 Linux SSH 실습, Chromium 데스크톱·모바일 검사를 실행합니다. 원본 실제 로그·패킷·키는 업로드하지 않으며 실습 요약과 분석 보고서, 브라우저 스크린샷을 아티팩트로 남깁니다. 로컬 검증과 원격 CI 실행 상태는 [검증 기록](docs/VERIFICATION.md)에 구분해서 기록합니다.

## 다음 단계

4단계 확장 코드가 포함되어 있습니다. 그 다음 후보는 대용량 로그 스트리밍, 중복 이벤트 식별, 다른 로그 소스 연결입니다. [확장 상태와 다음 아이디어](docs/EXTENSION_IDEAS.md)에 정리했습니다.

## 참고 자료

- [Python argparse](https://docs.python.org/3/library/argparse.html): CLI 옵션과 도움말
- [dpkt](https://github.com/kbandla/dpkt): PCAP/PCAPNG와 네트워크 프로토콜 해석
- [systemd journal 필드](https://www.freedesktop.org/software/systemd/man/latest/systemd.journal-fields.html): 네이티브 journal 입력
- [OpenSSH sshd_config](https://man.openbsd.org/sshd_config): 일회성 실습 서버 설정
- 웹 아이콘: [Lucide](https://lucide.dev), 라이선스는 src/netsec/web/assets/LUCIDE-LICENSE.txt에 포함
- [GitHub checkout v4](https://github.com/actions/checkout/tree/v4), [setup-python v5](https://github.com/actions/setup-python/tree/v5), [upload-artifact v4](https://github.com/actions/upload-artifact/tree/v4): 자동 검사에 사용하는 공식 Actions
