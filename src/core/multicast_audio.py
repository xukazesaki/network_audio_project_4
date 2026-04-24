import socket
import struct
from typing import Optional, Tuple

from src.core.config import (
    MCAST_BUFFER_SIZE,
    MCAST_GRP,
    MCAST_LOOPBACK,
    MCAST_PORT,
    MCAST_TTL,
)


class MulticastSender:
    """UDP 组播发送端：负责把麦克风音频发到组播组。"""

    def __init__(
        self,
        group_ip: str = MCAST_GRP,
        port: int = MCAST_PORT,
        ttl: int = MCAST_TTL,
        loopback: bool = MCAST_LOOPBACK,
    ):
        self.group_ip = group_ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # TTL 决定组播报文可跨越的路由跳数；局域网实验 1~2 即可
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

        # 是否接收自己发出的组播，关闭可避免“自己听到自己”的回声
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_LOOP,
            1 if loopback else 0,
        )

    def send(self, data: bytes) -> None:
        if not data:
            return
        self.sock.sendto(data, (self.group_ip, self.port))

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass
    
    

class MulticastReceiver:
    """UDP 组播接收端：负责加入组播组并接收语音数据。"""

    def __init__(
        self,
        group_ip: str = MCAST_GRP,
        port: int = MCAST_PORT,
        buffer_size: int = MCAST_BUFFER_SIZE,
    ):
        self.group_ip = group_ip
        self.port = port
        self.buffer_size = buffer_size

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Windows / Linux 下允许多个客户端同时绑定同一组播端口
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定到本机任意网卡上的该端口
        self.sock.bind(("", self.port))

        # 加入组播组
        membership = struct.pack(
            "4s4s",
            socket.inet_aton(self.group_ip),
            socket.inet_aton("0.0.0.0"),
        )
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)

        # 设超时，便于线程优雅退出
        self.sock.settimeout(0.5)

    def recv(self) -> Tuple[Optional[bytes], Optional[Tuple[str, int]]]:
        try:
            data, addr = self.sock.recvfrom(self.buffer_size)
            return data, addr
        except socket.timeout:
            return None, None
        except OSError:
            return None, None

    def close(self) -> None:
        try:
            membership = struct.pack(
                "4s4s",
                socket.inet_aton(self.group_ip),
                socket.inet_aton("0.0.0.0"),
            )
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, membership)
        except Exception:
            pass

        try:
            self.sock.close()
        except Exception:
            pass

    