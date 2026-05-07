import json
import socket
import struct
import time
from typing import Any, Dict, Optional, Tuple

from src.core.config import (
    MCAST_BUFFER_SIZE,
    MCAST_GRP,
    MCAST_INTERFACE_IP,
    MCAST_LOOPBACK,
    MCAST_PORT,
    MCAST_TTL,
)


from .protocol import _encode_packet, _decode_packet

MCAST_MAGIC = b"MCA1"
MCAST_PREFIX_STRUCT = struct.Struct("!4sH")


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


'''class MulticastSender:
    """UDP 组播发送端：负责把麦克风音频发到组播组。"""

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
        self.interface_ip = interface_ip
        self.sender_id = sender_id or "unknown"
        self.sequence = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # TTL 决定组播报文可跨越的路由跳数；局域网实验 1~2 即可
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

        # 是否接收自己发出的组播，关闭可避免“自己听到自己”的回声
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_LOOP,
            1 if loopback else 0,
        )

        # On multi-homed hosts, force multicast to use the intended NIC.
        if self.interface_ip and self.interface_ip != "0.0.0.0":
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
            pass'''


class MulticastSender:
    def __init__(self, sender_id, group_ip=MCAST_GRP, port=MCAST_PORT):
        self.sender_id = sender_id
        self.group_ip = group_ip
        self.port = port
        self.dest = (group_ip, port)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        
        # ✅ 允许组播发送
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send(self, audio_data):
        try:
            packet = _encode_packet(audio_data, sender=self.sender_id)
            self.sock.sendto(packet, self.dest)
        except Exception:
            pass

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


'''class MulticastReceiver:    """UDP 组播接收端：负责加入组播组并接收语音数据。"""

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
        self.interface_ip = interface_ip

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Windows / Linux 下允许多个客户端同时绑定同一组播端口
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定到本机任意网卡上的该端口
        self.sock.bind(("", self.port))

        # 加入组播组
        membership = struct.pack(
            "4s4s",
            socket.inet_aton(self.group_ip),
            socket.inet_aton(self.interface_ip),
        )
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)

        # 设超时，便于线程优雅退出
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
'''
class MulticastReceiver:
    """UDP 组播接收端：负责加入组播组并接收语音数据。"""

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
        self.interface_ip = interface_ip

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # 允许端口复用
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # ✅ 修复1：绑定 0.0.0.0 让所有网卡都能收到（别人电脑才能听到）
        self.sock.bind(('0.0.0.0', self.port))

        # ✅ 修复2：标准组播加入格式（跨平台必用）
        mreq = struct.pack("4sl", socket.inet_aton(self.group_ip), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # 超时
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
            # 退出组播（用修复后的格式）
            mreq = struct.pack("4sl", socket.inet_aton(self.group_ip), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except Exception:
            pass

        try:
            self.sock.close()
        except Exception:
            pass