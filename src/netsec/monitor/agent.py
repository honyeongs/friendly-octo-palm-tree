"""File polling adapter; stable identities survive append, retries and restarts."""

import hashlib
import json
import os
import time
from collections import Counter

from netsec.parsers.input import read_auth_log
from netsec.sdk import MonitorClient


def collect(client, path, input_format):
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Agent file limit is 20MB; rotate or export a smaller journal interval")
    parsed, _ = read_auth_log(path, input_format)
    occurrences = Counter()
    queued = 0
    for event in parsed.events:
        fields = {"timestamp": event.timestamp.isoformat(), "host": event.host, "source_ip": event.source_ip,
                  "username": event.username, "method": event.method, "outcome": "success" if event.outcome == "accepted" else "failure"}
        stable = json.dumps(fields, sort_keys=True)
        occurrences[stable] += 1
        event_id = hashlib.sha256((stable + ":" + str(occurrences[stable])).encode()).hexdigest()
        if client.emit(**fields, event_id=event_id, remember=True) is None:
            raise ValueError("Agent outbox is full or unavailable; resolve it before continuing")
        queued += 1
    return queued


def run(args):
    key = os.getenv("NETSEC_SOURCE_KEY", "")
    if not key:
        raise ValueError("Set NETSEC_SOURCE_KEY to the source key from the administration screen")
    client = MonitorClient(args.endpoint, key, args.outbox)
    try:
        while True:
            collect(client, args.input, args.format)
            delivered = client.flush()
            print(json.dumps({"delivered": delivered, "outbox": client.status()}), flush=True)
            if not args.follow:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    return 0
