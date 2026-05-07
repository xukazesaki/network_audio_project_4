import socket
import struct
import json
from typing import Optional, Tuple, Dict, Any

from src.core.config import (
    MCAST_BUFFER_SIZE,
    MCAST_GRP,
    MCAST_LOOPBACK,
    MCAST_PORT,
    MCAST_TTL,
)

def _encode_packet(audio_data: bytes, sender: str = "unknown") -> bytes:
    header = json.dumps({"sender": sender}).encode("utf-8")
    header_len = struct.pack(">I", len(header))
    return header_len + header + audio_data

def _decode_packet(raw_data: bytes):
    try:
        header_len = struct.unpack(">I", raw_data[:4])[0]
        header = json.loads(raw_data[4:4+header_len].decode("utf-8"))
        payload = raw_data[4+header_len:]
        return header, payload
    except:
        return None, None

class MulticastSender:
    def __init__(self, sender_id, group_ip=MCAST_GRP, port=MCAST_PORT, ttl=MCAST_TTL, loopback=MCAST_LOOPBACK):
        self.sender_id = sender_id
        self.group_ip = group_ip
        self.port = port
        self.dest = (group_ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1 if loopback else 0)

    def send(self, audio_data):
        try:
            packet = _encode_packet(audio_data, sender=self.sender_id)
            self.sock.sendto(packet, self.dest)
        except:
            pass

    def close(self):
        try:
            self.sock.close()
        except:
            pass

class MulticastReceiver:
    def __init__(self, group_ip=MCAST_GRP, port=MCAST_PORT, buffer_size=MCAST_BUFFER_SIZE):
        self.group_ip = group_ip
        self.port = port
        self.buffer_size = buffer_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', self.port))
        mreq = struct.pack("4sl", socket.inet_aton(self.group_ip), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.sock.settimeout(0.5)

    def recv(self):
        try:
            raw_packet, addr = self.sock.recvfrom(self.buffer_size)
            header, payload = _decode_packet(raw_packet)
            return payload, addr, header
        except:
            return None, None, None

    def close(self):
        try:
            mreq = struct.pack("4sl", socket.inet_aton(self.group_ip), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except:
            pass
        try:
            self.sock.close()
        except:
            pass