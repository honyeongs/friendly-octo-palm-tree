import importlib.util
import socket
import tempfile
import unittest
from pathlib import Path

from netsec.analysis import analyze_ssh
from netsec.packets.analysis import analyze_capture
from netsec.packets.reader import read_capture

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("dpkt"), "Install .[packets] for capture tests")
class PacketTests(unittest.TestCase):
    def test_pcap_and_pcapng_have_same_transport_counts(self):
        for suffix in ("pcap", "pcapng"):
            with self.subTest(suffix=suffix):
                capture = read_capture(ROOT / f"samples/packets/demo.{suffix}")
                report = analyze_capture(capture, source="test", server_ip="192.0.2.100")
                stats = report["statistics"]
                self.assertEqual((stats["total_packets"], stats["syn_packets"], stats["syn_ack_packets"]), (14, 7, 6))
                self.assertEqual((stats["connection_attempts"], stats["syn_retransmissions"], stats["reset_packets"]), (6, 1, 1))

    def test_auth_capture_links_and_native_journal(self):
        report = analyze_ssh(ROOT / "samples/ssh/journal.jsonl", pcap=ROOT / "samples/packets/demo.pcap", server_ip="192.0.2.100")
        self.assertEqual(report["input_format"], "journal")
        self.assertEqual(len(report["success_after_failures"]), 1)
        linked, missing = report["network"]["finding_links"]
        self.assertEqual((linked["connection_attempts"], linked["syn_retransmissions"]), (5, 1))
        self.assertTrue(linked["matched"])
        self.assertFalse(missing["matched"])

    def test_unrelated_server_not_linked(self):
        report = analyze_ssh(ROOT / "samples/ssh/journal.jsonl", pcap=ROOT / "samples/packets/demo.pcap", server_ip="192.0.2.200")
        self.assertTrue(all(not item["matched"] for item in report["network"]["finding_links"]))

    def test_capture_requires_mapping(self):
        with self.assertRaisesRegex(ValueError, "requires --server-ip"):
            analyze_ssh(ROOT / "samples/ssh/demo.log", pcap=ROOT / "samples/packets/demo.pcap")
        with self.assertRaisesRegex(ValueError, "does not match"):
            analyze_ssh(ROOT / "samples/ssh/demo.log", pcap=ROOT / "samples/packets/demo.pcap", server_ip="192.0.2.100", server_host="wrong")

    def test_multiple_hosts_require_explicit_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multi.log"
            original = (ROOT / "samples/ssh/correlated.log").read_text()
            path.write_text(original + original.replace(" lab ", " other "))
            with self.assertRaisesRegex(ValueError, "Multiple log hosts"):
                analyze_ssh(path, pcap=ROOT / "samples/packets/demo.pcap", server_ip="192.0.2.100")
            report = analyze_ssh(path, pcap=ROOT / "samples/packets/demo.pcap", server_ip="192.0.2.100", server_host="lab")
            self.assertTrue(all(item["host"] == "lab" for item in report["network"]["finding_links"]))

    def test_invalid_and_truncated_captures(self):
        original = (ROOT / "samples/packets/demo.pcapng").read_bytes()
        for data in (b"bad", original[:-1], original + original):
            with self.subTest(size=len(data)), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.pcapng"
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    read_capture(path)

    def test_unsupported_linktype_rejected(self):
        import dpkt
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.pcap"
            with path.open("wb") as stream:
                dpkt.pcap.Writer(stream, linktype=999)
            with self.assertRaisesRegex(ValueError, "link type"):
                read_capture(path)

    def test_ipv6_raw_and_cooked_links(self):
        import dpkt
        tcp = dpkt.tcp.TCP(sport=50001, dport=22, flags=dpkt.tcp.TH_SYN, seq=1)
        ip = dpkt.ip6.IP6(src=socket.inet_pton(socket.AF_INET6, "2001:db8::10"),
                          dst=socket.inet_pton(socket.AF_INET6, "2001:db8::100"), nxt=6, data=tcp)
        ip.plen = len(tcp)
        formats = [(101, bytes(ip)), (113, bytes(dpkt.sll.SLL(ethtype=0x86dd, data=ip))),
                   (276, bytes(dpkt.sll2.SLL2(ethtype=0x86dd, data=ip)))]
        for linktype, data in formats:
            with self.subTest(linktype=linktype), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "test.pcap"
                with path.open("wb") as stream:
                    dpkt.pcap.Writer(stream, linktype=linktype).writepkt(data, ts=1791676800)
                report = analyze_capture(read_capture(path), source="test", server_ip="2001:db8::100")
                self.assertEqual(report["statistics"]["connection_attempts"], 1)

    def test_non_tcp_packet_is_not_connection_attempt(self):
        import dpkt
        udp = dpkt.udp.UDP(sport=1000, dport=22, data=b"test")
        udp.ulen = len(udp)
        ip = dpkt.ip.IP(src=socket.inet_aton("192.0.2.10"), dst=socket.inet_aton("192.0.2.100"), p=17, data=udp)
        ip.len = len(ip)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "udp.pcap"
            with path.open("wb") as stream:
                dpkt.pcap.Writer(stream, linktype=101).writepkt(bytes(ip), ts=1791676800)
            capture = read_capture(path)
            self.assertEqual((capture.non_tcp_packets, len(capture.packets)), (1, 0))
