"""Command-line orchestration; parsing and rules live in their own modules."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from netsec import __version__
from netsec.analysis import analyze_pcap, analyze_ssh
from netsec.reporters.json_report import serialize_report, write_report


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _window_seconds(value: str) -> int:
    number = _positive_int(value)
    if number > 86400:
        raise argparse.ArgumentTypeError("must be at most 86400 seconds")
    return number


def _port(value: str) -> int:
    number = _positive_int(value)
    if number > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return number


def _margin(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("margin must be an integer") from error
    if not 0 <= number <= 86400:
        raise argparse.ArgumentTypeError("margin must be between 0 and 86400")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netsec", description="Offline SSH log analysis")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze-ssh", help="Analyze timestamped OpenSSH logs")
    analyze.add_argument("input", type=Path, help="UTF-8 log with timezone-aware ISO timestamps")
    analyze.add_argument("--window-seconds", type=_window_seconds, default=60)
    analyze.add_argument("--threshold", type=_positive_int, default=5)
    analyze.add_argument("--format", choices=("auto", "openssh", "journal"), default="auto")
    analyze.add_argument("--success-window-seconds", type=_window_seconds, default=300)
    analyze.add_argument("--pcap", type=Path)
    analyze.add_argument("--server-ip")
    analyze.add_argument("--server-host")
    analyze.add_argument("--server-port", type=_port, default=22)
    analyze.add_argument("--packet-margin-seconds", type=_margin, default=5)
    packets = commands.add_parser("analyze-pcap", help="Summarize offline TCP transport evidence")
    packets.add_argument("input", type=Path)
    packets.add_argument("--server-ip", required=True)
    packets.add_argument("--server-port", type=_port, default=22)
    for command in (analyze, packets):
        command.add_argument("--output", default="-", help="JSON output path, or - for stdout")
        command.add_argument("--overwrite", action="store_true", help="Replace an existing output file")
    web = commands.add_parser("serve", help="Open the local report comparison tool")
    web.add_argument("--port", type=_port, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from netsec.server import serve
            serve(args.port)
            return 0
        output = None if args.output == "-" else Path(args.output)
        if output is not None:
            inputs = [args.input] + ([args.pcap] if getattr(args, "pcap", None) else [])
            for source in inputs:
                same_path = output.resolve() == source.resolve()
                same_file = output.exists() and source.exists() and output.samefile(source)
                if same_path or same_file:
                    raise ValueError("Output must not replace the input log or capture")
        if args.command == "analyze-ssh":
            report = analyze_ssh(
                args.input, input_format=args.format, window_seconds=args.window_seconds,
                threshold=args.threshold, success_window_seconds=args.success_window_seconds,
                pcap=args.pcap, server_ip=args.server_ip, server_host=args.server_host,
                server_port=args.server_port, packet_margin_seconds=args.packet_margin_seconds,
            )
        else:
            report = analyze_pcap(args.input, server_ip=args.server_ip, server_port=args.server_port)
        if output is None:
            sys.stdout.write(serialize_report(report))
        else:
            write_report(report, output, overwrite=args.overwrite)
        stats = report["statistics"]
        if args.command == "analyze-ssh":
            print(f"Analyzed {stats['parsed_events']} events: {stats['failed_events']} failed, "
                  f"{stats['accepted_events']} accepted; {stats['finding_count']} finding(s), "
                  f"{stats['correlation_count']} success correlation(s). "
                  f"Ignored {stats['ignored_lines']}, malformed {stats['malformed_lines']} line(s).",
                  file=sys.stderr)
        else:
            print(f"Analyzed {stats['total_packets']} packets: "
                  f"{stats['connection_attempts']} TCP attempt(s), "
                  f"{stats['malformed_packets']} malformed packet(s).", file=sys.stderr)
        if stats.get("malformed_lines"):
            print("Warning: malformed authentication lines were excluded; inspect "
                  "statistics.malformed_line_numbers in the report.", file=sys.stderr)
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"netsec: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
