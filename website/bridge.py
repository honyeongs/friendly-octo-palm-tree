"""Run the original offline SSH/PCAP analyzer in the ephemeral WASM filesystem."""
import json
from pathlib import Path
from netsec.analysis import analyze_ssh

def bounded_integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid numeric option")
    return value

def dispatch(route, body, metadata, auxiliary):
    if route == "/api/health":
        return {"status": 200, "data": {"status": "ready"}}
    if route != "/api/ssh" or not body or len(body) > 8 * 1024 * 1024 or len(auxiliary) > 8 * 1024 * 1024:
        raise ValueError("Invalid input")
    # Fixed virtual paths never use a user-supplied filename; cleanup runs even on parse failure.
    log = Path("/session-input.log")
    capture = Path("/session-capture.pcap")
    try:
        log.write_bytes(body)
        if auxiliary:
            capture.write_bytes(auxiliary)
        report = analyze_ssh(
            log, input_format=metadata.get("format", "auto"),
            window_seconds=bounded_integer(metadata.get("window", 60), 1, 86400),
            threshold=bounded_integer(metadata.get("threshold", 5), 1, 10000),
            success_window_seconds=bounded_integer(metadata.get("success", 300), 1, 86400),
            pcap=capture if auxiliary else None,
            server_ip=metadata.get("server_ip") or None, server_host=metadata.get("server_host") or None,
        )
        report["source"] = str(metadata.get("name", "selected-log"))[:255]
        if "network" in report:
            report["network"]["source"] = str(metadata.get("capture_name", "selected-capture"))[:255]
        return {"status": 200, "data": report}
    finally:
        log.unlink(missing_ok=True)
        capture.unlink(missing_ok=True)

def _dispatch_json(route, body, metadata, auxiliary):
    try:
        result = dispatch(route, body, json.loads(metadata), auxiliary)
    except (ValueError, TypeError, UnicodeError, OSError):
        result = {"status": 400, "data": {"error": "로그·PCAP 형식 또는 분석 조건을 확인해주세요. 로그에는 연도와 시간대가 필요합니다."}}
    return json.dumps(result, ensure_ascii=True, allow_nan=False)
