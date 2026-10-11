"""Create a disposable loopback SSH/journald/packet-capture integration case."""

import argparse
import getpass
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from netsec.analysis import analyze_ssh
from netsec.reporters.json_report import write_report


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30, **kwargs)


def wait_for_server(port, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Disposable SSH server did not start")


def run(output: Path, port: int):
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Run this isolated lab on Linux with sudo")
    required = ("systemd-run", "systemctl", "journalctl", "sshd", "ssh", "ssh-keygen", "tcpdump")
    executables = {name: shutil.which(name) for name in required}
    missing = [name for name, path in executables.items() if path is None]
    if missing:
        raise RuntimeError("Missing lab programs: " + ", ".join(missing))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    output.mkdir(parents=True, exist_ok=False)
    unit = "netsec-lab-" + uuid.uuid4().hex
    capture = None
    started = False
    username = os.environ.get("SUDO_USER") or getpass.getuser()
    Path("/run/sshd").mkdir(mode=0o755, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="netsec-ssh-") as temporary:
            directory = Path(temporary)
            directory.chmod(0o755)
            for name in ("host_key", "valid_key", "rejected_key"):
                command([executables["ssh-keygen"], "-q", "-t", "ed25519", "-N", "", "-f", str(directory / name)])
            authorized = directory / "authorized_keys"
            authorized.write_text((directory / "valid_key.pub").read_text(), encoding="utf-8")
            authorized.chmod(0o644)
            config = directory / "sshd_config"
            config.write_text(
                f"Port {port}\nListenAddress 127.0.0.1\nHostKey {directory / 'host_key'}\n"
                f"PidFile {directory / 'sshd.pid'}\nAuthorizedKeysFile {authorized}\n"
                "PubkeyAuthentication yes\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n"
                "UsePAM yes\nStrictModes no\nPermitRootLogin prohibit-password\n"
                "LogLevel VERBOSE\nAllowTcpForwarding no\nX11Forwarding no\n",
                encoding="utf-8",
            )
            command([executables["sshd"], "-t", "-f", str(config)])
            command([executables["systemd-run"], "--quiet", "--unit", unit,
                     "--property=Type=exec", "--property=SyslogIdentifier=sshd",
                     "--property=StandardOutput=journal", "--property=StandardError=journal",
                     executables["sshd"], "-D", "-e", "-f", str(config)])
            started = True
            wait_for_server(port)
            capture_log = (output / "capture.log").open("w", encoding="utf-8")
            try:
                capture = subprocess.Popen(
                    [executables["tcpdump"], "-U", "-i", "lo", "-w", str(output / "traffic.pcap"),
                     "tcp", "port", str(port)], stdout=capture_log, stderr=capture_log,
                )
                time.sleep(0.6)
                if capture.poll() is not None:
                    raise RuntimeError("tcpdump did not start; inspect capture.log")
                attempts = []
                for index in range(6):
                    key = directory / ("valid_key" if index == 5 else "rejected_key")
                    result = subprocess.run([
                        executables["ssh"], "-p", str(port), "-i", str(key),
                        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
                        "-o", "PreferredAuthentications=publickey", "-o", "ConnectTimeout=5",
                        "-o", "StrictHostKeyChecking=accept-new",
                        "-o", f"UserKnownHostsFile={directory / 'known_hosts'}",
                        f"{username}@127.0.0.1", "true",
                    ], capture_output=True, text=True, timeout=15)
                    attempts.append({"attempt": index + 1, "exit_code": result.returncode})
                    if (index < 5 and result.returncode != 255) or (index == 5 and result.returncode != 0):
                        raise RuntimeError(f"Unexpected SSH result for attempt {index + 1}: {result.stderr}")
                time.sleep(0.3)
            finally:
                if capture is not None and capture.poll() is None:
                    capture.send_signal(signal.SIGINT)
                    capture.wait(timeout=10)
                capture_log.close()
            command([executables["journalctl"], "--sync"])
            exported = command([executables["journalctl"], "-u", unit, "-o", "json", "--no-pager"])
            journal = output / "ssh.journal.jsonl"
            journal.write_text(exported.stdout, encoding="utf-8")
            report = analyze_ssh(journal, input_format="journal", pcap=output / "traffic.pcap",
                                 server_ip="127.0.0.1", server_port=port)
            stats = report["statistics"]
            if stats["failed_events"] < 5 or stats["accepted_events"] != 1:
                raise RuntimeError(f"Unexpected real authentication counts: {stats}")
            if not report["success_after_failures"]:
                raise RuntimeError("Real authentication correlation was not detected")
            if report["network"]["statistics"]["connection_attempts"] < 6:
                raise RuntimeError("Real capture is missing TCP attempts")
            if not any(link["matched"] for link in report["network"]["finding_links"]):
                raise RuntimeError("Real capture did not correlate with SSH findings")
            write_report(report, output / "report.json")
            metadata = {
                "case": "Real loopback OpenSSH authentication with native journal and tcpdump",
                "synthetic": False, "server_port": port, "attempts": attempts,
                "ssh_version": subprocess.run([executables["ssh"], "-V"], capture_output=True, text=True).stderr.strip(),
                "failed_events": stats["failed_events"], "accepted_events": stats["accepted_events"],
                "finding_count": stats["finding_count"], "correlation_count": stats["correlation_count"],
                "packet_count": report["network"]["statistics"]["total_packets"],
            }
            (output / "case.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(metadata, indent=2))
    finally:
        if started:
            if sys.exc_info()[0] is not None:
                diagnostic = subprocess.run(
                    [executables["journalctl"], "-u", unit, "-o", "cat", "--no-pager"],
                    capture_output=True, text=True, timeout=15,
                )
                print(diagnostic.stdout, file=sys.stderr)
            subprocess.run([executables["systemctl"], "stop", unit], capture_output=True, timeout=15)
            subprocess.run([executables["systemctl"], "reset-failed", unit], capture_output=True, timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=22222)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port between 1024 and 65535")
    try:
        run(args.output, args.port)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        raise SystemExit(f"Lab failed: {error}")
