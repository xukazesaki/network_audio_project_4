import json
import socket
import struct
import time
from typing import Any, Dict, Optional, Tuple

from src.core.config import (
    HOST,
    MCAST_BUFFER_SIZE,
    MCAST_GRP,
    MCAST_INTERFACE_IP,
    MCAST_LOOPBACK,
    MCAST_PORT,
    MCAST_TTL,
    PORT,
)


MCAST_MAGIC = b"MCA1"
MCAST_PREFIX_STRUCT = struct.Struct("!4sH")


def _resolve_interface_ip(interface_ip: str = MCAST_INTERFACE_IP) -> str:
    if interface_ip and interface_ip != "0.0.0.0":
        return interface_ip

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((HOST, PORT))
        return probe.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        probe.close()


def _encode_packet_header(header: Dict[str, Any]) -> bytes:
    header_bytes = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MCAST_PREFIX_STRUCT.pack(MCAST_MAGIC, len(header_bytes)) + header_bytes


def _decode_packet(raw_packet: bytes) -> Tuple[Optional[Dict[str, Any]], Optional[bytes]]:
    if len(raw_packet) < MCAST_PREFIX_STRUCT.size:
        return None, None

    magic, header_len = MCAST_PREFIX_STRUCT.unpack(raw_packet[: MCAST_PREFIX_STRUCT.size])
    if magic != MCAST_MAGIC:
        return None, None

    header_end = MCAST_PREFIX_STRUCT.size + header_len
    if len(raw_packet) < header_end:
        return None, None

    try:
        header = json.loads(raw_packet[MCAST_PREFIX_STRUCT.size:header_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None

    payload = raw_packet[header_end:]
    if int(header.get("payload_len", -1)) != len(payload):
        return None, None

    return header, payload


class MulticastSender:
    def __init__(
        self,
        group_ip: str = MCAST_GRP,
        port: int = MCAST_PORT,
        ttl: int = MCAST_TTL,
        loopback: bool = MCAST_LOOPBACK,
        interface_ip: str = MCAST_INTERFACE_IP,
        sender_id: str = "",
    ):
        self.group_ip = group_ip
        self.port = port
        self.interface_ip = _resolve_interface_ip(interface_ip)
        self.sender_id = sender_id or "unknown"
        self.sequence = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("B", ttl))
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_LOOP,
            struct.pack("B", 1 if loopback else 0),
        )

        if self.interface_ip != "0.0.0.0":
            self.sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_IF,
                socket.inet_aton(self.interface_ip),
            )

    def send(self, data: bytes) -> None:
        if not data:
            return

        header = {
            "version": 1,
            "sender": self.sender_id,
            "seq": self.sequence,
            "timestamp_ms": int(time.time() * 1000),
            "payload_len": len(data),
        }
        packet = _encode_packet_header(header) + data
        self.sock.sendto(packet, (self.group_ip, self.port))
        self.sequence += 1

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


class MulticastReceiver:
    def __init__(
        self,
        group_ip: str = MCAST_GRP,
        port: int = MCAST_PORT,
        buffer_size: int = MCAST_BUFFER_SIZE,
        interface_ip: str = MCAST_INTERFACE_IP,
    ):
        self.group_ip = group_ip
        self.port = port
        self.buffer_size = buffer_size
        self.interface_ip = _resolve_interface_ip(interface_ip)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        self.sock.bind(("", self.port))
        membership = struct.pack(
            "4s4s",
            socket.inet_aton(self.group_ip),
            socket.inet_aton(self.interface_ip),
        )
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        self.sock.settimeout(0.5)

    def recv(self) -> Tuple[Optional[bytes], Optional[Tuple[str, int]], Optional[Dict[str, Any]]]:
        try:
            raw_packet, addr = self.sock.recvfrom(self.buffer_size)
            header, payload = _decode_packet(raw_packet)
            if header is None or payload is None:
                return None, addr, None
            return payload, addr, header
        except socket.timeout:
            return None, None, None
        except OSError:
            return None, None, None

    def close(self) -> None:
        try:
            membership = struct.pack(
                "4s4s",
                socket.inet_aton(self.group_ip),
                socket.inet_aton(self.interface_ip),
            )
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, membership)
        except Exception:
            pass

        try:
            self.sock.close()
        except Exception:
            pass
