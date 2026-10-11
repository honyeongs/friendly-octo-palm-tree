"""Connect input adapters, rules and optional transport evidence."""

from pathlib import Path

from netsec.detectors.repeated_failures import detect_repeated_failures
from netsec.detectors.success_after_failures import correlate_successes
from netsec.parsers.input import read_auth_log
from netsec.reporters.correlations import success_records
from netsec.reporters.json_report import build_report


def analyze_ssh(
    path: Path, *, input_format="auto", window_seconds=60, threshold=5,
    success_window_seconds=300, pcap=None, server_ip=None, server_host=None,
    server_port=22, packet_margin_seconds=5,
):
    if pcap is None and (server_ip is not None or server_host is not None):
        raise ValueError("--server-ip and --server-host require --pcap")
    if pcap is not None and not server_ip:
        raise ValueError("--pcap requires --server-ip")
    parsed, selected = read_auth_log(path, input_format)
    if not parsed.events:
        raise ValueError("No supported SSH authentication events found. Use ISO 8601 "
                         "timestamps with a UTC offset or Z, or journalctl -o json; "
                         "see docs/detection-rules.md")
    findings = detect_repeated_failures(parsed.events, window_seconds=window_seconds, threshold=threshold)
    correlations = correlate_successes(parsed.events, window_seconds=window_seconds,
                                       threshold=threshold, success_window_seconds=success_window_seconds)
    report = build_report(source=path.name, statistics=parsed.statistics, findings=findings,
                          window_seconds=window_seconds, threshold=threshold)
    report.update({"schema_version": "1.1", "report_type": "ssh", "input_format": selected,
                   "success_after_failures": success_records(correlations)})
    report["parameters"]["success_window_seconds"] = success_window_seconds
    report["statistics"]["correlation_count"] = len(correlations)
    if pcap is not None:
        from netsec.packets.analysis import analyze_capture, link_findings
        from netsec.packets.reader import read_capture
        hosts = {event.host for event in parsed.events}
        if server_host is None:
            if len(hosts) != 1:
                raise ValueError("Multiple log hosts: specify --server-host to map the capture")
            server_host = next(iter(hosts))
        if server_host not in hosts:
            raise ValueError("--server-host does not match a host in the authentication log")
        capture = read_capture(Path(pcap))
        network = analyze_capture(capture, source=Path(pcap).name, server_ip=server_ip, server_port=server_port)
        network["server_host"] = server_host
        network["margin_seconds"] = packet_margin_seconds
        network["finding_links"] = link_findings(
            findings, capture, server_host=server_host, server_ip=server_ip,
            server_port=server_port, margin_seconds=packet_margin_seconds,
        )
        report["network"] = network
    return report


def analyze_pcap(path: Path, *, server_ip: str, server_port: int = 22):
    from netsec.packets.analysis import analyze_capture
    from netsec.packets.reader import read_capture
    network = analyze_capture(read_capture(path), source=path.name,
                              server_ip=server_ip, server_port=server_port)
    return {"schema_version": "1.1", "report_type": "tcp", "rule": "tcp_transport_observations",
            "source": path.name, "parameters": {}, "statistics": network["statistics"],
            "findings": [], "success_after_failures": [], "network": network}
