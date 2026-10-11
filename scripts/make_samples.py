"""Rebuild deterministic, explicitly synthetic journal/capture/viewer samples."""

import json
import socket
from datetime import datetime, timezone
from pathlib import Path

import dpkt

from netsec.analysis import analyze_ssh
from netsec.reporters.json_report import write_report

ROOT = Path(__file__).resolve().parents[1]


def frame(source, destination, source_port, destination_port, flags, sequence):
    tcp = dpkt.tcp.TCP(sport=source_port, dport=destination_port, flags=flags, seq=sequence)
    if ":" in source:
        network = dpkt.ip6.IP6(src=socket.inet_pton(socket.AF_INET6, source),
                              dst=socket.inet_pton(socket.AF_INET6, destination), nxt=6, data=tcp)
        network.plen = len(tcp)
        kind = dpkt.ethernet.ETH_TYPE_IP6
    else:
        network = dpkt.ip.IP(src=socket.inet_aton(source), dst=socket.inet_aton(destination), p=6, data=tcp)
        network.len = len(network)
        kind = dpkt.ethernet.ETH_TYPE_IP
    return bytes(dpkt.ethernet.Ethernet(src=b"\x02\x00\x00\x00\x00\x01",
                                      dst=b"\x02\x00\x00\x00\x00\x02", type=kind, data=network))


def main():
    packets = ROOT / "samples/packets"
    packets.mkdir(exist_ok=True)
    base = datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()
    entries = []
    for index in range(6):
        stamp = base + 59 + index * 10
        port = 50001 + index
        syn = frame("192.0.2.10", "192.0.2.100", port, 22, dpkt.tcp.TH_SYN, index + 1000)
        entries.append((stamp, syn))
        if index == 0:
            entries.append((stamp + 0.1, syn))
        entries.append((stamp + 0.2, frame("192.0.2.100", "192.0.2.10", 22, port,
                                          dpkt.tcp.TH_SYN | dpkt.tcp.TH_ACK, index + 2000)))
    entries.append((base + 61, frame("192.0.2.100", "192.0.2.10", 22, 50001, dpkt.tcp.TH_RST, 3000)))
    for name, writer_type in (("demo.pcap", dpkt.pcap.Writer), ("demo.pcapng", dpkt.pcapng.Writer)):
        with (packets / name).open("wb") as stream:
            writer = writer_type(stream)
            for stamp, packet in sorted(entries, key=lambda item: item[0]):
                writer.writepkt(packet, ts=stamp)
    journal = ROOT / "samples/ssh/journal.jsonl"
    records = []
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for line in (ROOT / "samples/ssh/correlated.log").read_text(encoding="utf-8").splitlines():
        stamp, host, remainder = line.split(" ", 2)
        delta = datetime.fromisoformat(stamp).astimezone(timezone.utc) - epoch
        microseconds = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
        records.append({"__REALTIME_TIMESTAMP": str(microseconds), "_HOSTNAME": host,
                        "SYSLOG_IDENTIFIER": "sshd", "MESSAGE": remainder.split(": ", 1)[1]})
    journal.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    baseline = analyze_ssh(ROOT / "samples/ssh/normal.log")
    extended = analyze_ssh(journal, pcap=packets / "demo.pcap", server_ip="192.0.2.100")
    write_report(extended, ROOT / "samples/ssh/extended-report.json", overwrite=True)
    data = ROOT / "src/netsec/web/data"
    data.mkdir(exist_ok=True)
    write_report(baseline, data / "baseline.json", overwrite=True)
    write_report(extended, data / "extended.json", overwrite=True)
    print("Rebuilt synthetic capture, journal and web example reports")


if __name__ == "__main__":
    main()
