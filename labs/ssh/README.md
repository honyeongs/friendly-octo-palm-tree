# 실제 Linux SSH 실습

일회성 loopback SSH 서버에서 잘못된 공개키 인증 5회, 유효한 공개키 인증 1회를 생성한다. 실제 journald JSON과 tcpdump 캡처를 같은 시간대에서 분석하고 근거가 연결되는지 검증한다. 운영 SSH 서비스 설정은 수정하지 않는다.

systemd가 실행되는 Ubuntu/Debian에서 openssh-server, openssh-client, tcpdump가 필요하다. 프로젝트를 패킷 옵션과 함께 설치한다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[packets]'
sudo apt-get install openssh-server openssh-client tcpdump
sudo .venv/bin/python labs/ssh/run_lab.py --output lab-results
```

출력 폴더는 새 경로여야 한다. case.json은 실행 조건과 실제 이벤트 수, ssh.journal.jsonl은 원본 journal 내보내기, traffic.pcap은 실제 loopback 패킷, report.json은 통합 결과이다. 임시 인증키는 별도 임시 폴더에 만들고 실습 종료 시 삭제한다. 결과에는 실습 계정·호스트 정보가 있으므로 Git으로 추적하지 않는다.

실행기는 자신이 만든 systemd unit만 종료한다. SSH 서버는 127.0.0.1:22222에만 바인딩하고, 포트가 사용 중이면 시작 전에 실패한다. 다른 포트는 --port로 지정할 수 있다.

GitHub Actions의 linux-lab 작업은 이 절차를 실행하고 case.json과 report.json을 검증 아티팩트로 보관한다. 개인키, 원본 journal, 패킷은 업로드하지 않는다. 실제 통과 여부는 Actions 실행 결과를 확인해야 한다.
