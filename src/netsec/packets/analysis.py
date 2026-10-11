"""Summarize transport evidence without inferring encrypted authentication."""

from collections import defaultdict
from datetime import timedelta
from ipaddress import ip_address

from netsec.packets.models import Capture
from netsec.reporters.json_report import _utc

SYN, ACK, RST = 0x02, 0x10, 0x04


def packet_records(packets, server_ip: str, server_port: int):
    records = []
    for packet in packets:
        incoming = packet.destination_ip == server_ip and packet.destination_port == server_port
        outgoing = packet.source_ip == server_ip and packet.source_port == server_port
        if not incoming and not outgoing:
            continue
        if incoming and packet.flags & SYN and not packet.flags & ACK:
            kind = "syn"
        elif outgoing and packet.flags & SYN and packet.flags & ACK:
            kind = "syn_ack"
        elif packet.flags & RST:
            kind = "reset"
        else:
            continue
        records.append({
            "timestamp": _utc(packet.timestamp), "packet_number": packet.packet_number,
            "kind": kind, "direction": "to_server" if incoming else "from_server",
            "client_ip": packet.source_ip if incoming else packet.destination_ip,
            "client_port": packet.source_port if incoming else packet.destination_port,
            "sequence": packet.sequence,
        })
    return records


def summarize_records(records):
    syns = [item for item in records if item["kind"] == "syn"]
    attempts = {(item["client_ip"], item["client_port"], item["sequence"]) for item in syns}
    return {
        "syn_packets": len(syns), "connection_attempts": len(attempts),
        "syn_retransmissions": len(syns) - len(attempts),
        "syn_ack_packets": sum(item["kind"] == "syn_ack" for item in records),
        "reset_packets": sum(item["kind"] == "reset" for item in records),
    }


def analyze_capture(capture: Capture, *, source: str, server_ip: str, server_port: int = 22):
    address = str(ip_address(server_ip))
    if not 1 <= server_port <= 65535:
        raise ValueError("Server port must be between 1 and 65535")
    records = packet_records(capture.packets, address, server_port)
    groups = defaultdict(list)
    for record in records:
        groups[record["client_ip"]].append(record)
    return {
        "source": source, "server_ip": address, "server_port": server_port,
        "statistics": {"total_packets": capture.total_packets, "tcp_packets": len(capture.packets),
                       "non_tcp_packets": capture.non_tcp_packets,
                       "malformed_packets": capture.malformed_packets, **summarize_records(records)},
        "clients": [{"source_ip": ip, **summarize_records(items), "evidence": items}
                    for ip, items in sorted(groups.items())],
        "interpretation": "Transport observations only; SSH authentication is encrypted. "
                          "Missing responses may reflect incomplete capture, not failed connections.",
    }


def link_findings(findings, capture: Capture, *, server_host: str,
                  server_ip: str, server_port: int = 22, margin_seconds: int = 5):
    if type(margin_seconds) is not int or not 0 <= margin_seconds <= 86400:
        raise ValueError("Packet margin must be between 0 and 86400 seconds")
    address = str(ip_address(server_ip))
    links = []
    margin = timedelta(seconds=margin_seconds)
    for index, finding in enumerate(findings):
        if finding.host != server_host:
            continue
        packets = [packet for packet in capture.packets
                   if finding.evidence[0].timestamp - margin <= packet.timestamp <= finding.evidence[-1].timestamp + margin]
        records = [record for record in packet_records(packets, address, server_port)
                   if record["client_ip"] == finding.source_ip]
        links.append({
            "finding_index": index, "host": server_host, "source_ip": finding.source_ip,
            "matched": bool(records), **summarize_records(records), "evidence": records,
        })
    return links
