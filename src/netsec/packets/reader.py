"""Read supported capture containers and decode network protocols with dpkt."""

import socket
import struct
from datetime import datetime, timezone
from pathlib import Path

from netsec.packets.models import Capture, TcpPacket


def _dpkt():
    try:
        import dpkt
    except ImportError as error:
        raise ValueError('Packet analysis needs: python -m pip install ".[packets]"') from error
    return dpkt


def _check_pcapng(stream):
    """Reject interface changes dpkt's simple Reader cannot interpret correctly."""
    stream.seek(8)
    bom = stream.read(4)
    endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    sections = interfaces = 0
    while stream.tell() < size:
        position = stream.tell()
        header = stream.read(8)
        if len(header) != 8:
            raise ValueError("Truncated PCAPNG block")
        kind, length = struct.unpack(endian + "II", header)
        if length < 12 or length % 4 or position + length > size:
            raise ValueError("Invalid PCAPNG block length")
        if kind == 0x0A0D0D0A:
            sections += 1
        elif kind == 1:
            interfaces += 1
        elif kind in (2, 6):
            field_size = 2 if kind == 2 else 4
            field = stream.read(field_size)
            if len(field) != field_size or int.from_bytes(field, "little" if endian == "<" else "big") != 0:
                raise ValueError("PCAPNG requires a single interface with ID 0")
        elif kind == 3:
            raise ValueError("PCAPNG packets without timestamps are unsupported")
        stream.seek(position + length - 4)
        if struct.unpack(endian + "I", stream.read(4))[0] != length:
            raise ValueError("PCAPNG block lengths disagree")
    if sections != 1 or interfaces != 1:
        raise ValueError("PCAPNG requires exactly one section and one interface")
    stream.seek(0)


def read_capture(path: Path) -> Capture:
    dpkt = _dpkt()
    packets = []
    total = malformed = non_tcp = 0
    try:
        with path.open("rb") as stream:
            magic = stream.read(4)
            stream.seek(0)
            if magic == b"\x0a\x0d\x0d\x0a":
                _check_pcapng(stream)
                reader = dpkt.pcapng.Reader(stream)
            else:
                reader = dpkt.pcap.Reader(stream)
            linktype = reader.datalink()
            if linktype not in {0, 1, 12, 101, 108, 113, 276}:
                raise ValueError(f"Unsupported capture link type: {linktype}")
            for number, (stamp, data) in enumerate(reader, 1):
                total += 1
                try:
                    if linktype == 1:
                        network = dpkt.ethernet.Ethernet(data).data
                    elif linktype == 113:
                        network = dpkt.sll.SLL(data).data
                    elif linktype == 276:
                        network = dpkt.sll2.SLL2(data).data
                    elif linktype in {0, 108}:
                        network = dpkt.loopback.Loopback(data).data
                    else:
                        network = dpkt.ip6.IP6(data) if data[0] >> 4 == 6 else dpkt.ip.IP(data)
                    if not isinstance(network, (dpkt.ip.IP, dpkt.ip6.IP6)):
                        non_tcp += 1
                        continue
                    # Noninitial fragments cannot be interpreted as TCP headers.
                    if isinstance(network, dpkt.ip.IP) and (network.offset or network.mf):
                        non_tcp += 1
                        continue
                    tcp = network.data
                    if not isinstance(tcp, dpkt.tcp.TCP):
                        non_tcp += 1
                        continue
                    family = socket.AF_INET6 if isinstance(network, dpkt.ip6.IP6) else socket.AF_INET
                    packets.append(TcpPacket(
                        datetime.fromtimestamp(float(stamp), timezone.utc),
                        socket.inet_ntop(family, network.src), socket.inet_ntop(family, network.dst),
                        tcp.sport, tcp.dport, tcp.flags, tcp.seq, number,
                    ))
                except (dpkt.UnpackError, ValueError, IndexError, struct.error, OverflowError):
                    malformed += 1
    except (dpkt.UnpackError, struct.error) as error:
        raise ValueError(f"Invalid or truncated capture: {error}") from error
    return Capture(tuple(sorted(packets, key=lambda item: (item.timestamp, item.packet_number))),
                   total, non_tcp, malformed, linktype)
