from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TcpPacket:
    timestamp: datetime
    source_ip: str
    destination_ip: str
    source_port: int
    destination_port: int
    flags: int
    sequence: int
    packet_number: int


@dataclass(frozen=True)
class Capture:
    packets: tuple[TcpPacket, ...]
    total_packets: int
    non_tcp_packets: int
    malformed_packets: int
    linktype: int
