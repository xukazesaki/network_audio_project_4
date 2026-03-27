# protocol.py

import json
import os
import socket
import struct


def recvall(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            raise ConnectionError("连接已断开")
        data += packet
    return data


def send_json(sock: socket.socket, obj: dict):
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)))
    sock.sendall(raw)


def recv_json(sock: socket.socket) -> dict:
    header = recvall(sock, 4)
    msg_len = struct.unpack("!I", header)[0]
    raw = recvall(sock, msg_len)
    return json.loads(raw.decode("utf-8"))


def send_file_bytes(sock: socket.socket, file_path: str):
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            sock.sendall(chunk)


def send_bytes(sock: socket.socket, data: bytes):
    if data:
        sock.sendall(data)


def recv_file_bytes(sock: socket.socket, save_path: str, file_size: int):
    dir_name = os.path.dirname(save_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    remaining = file_size
    with open(save_path, "wb") as f:
        while remaining > 0:
            chunk = sock.recv(min(4096, remaining))
            if not chunk:
                raise ConnectionError("接收文件时连接断开")
            f.write(chunk)
            remaining -= len(chunk)


def recv_stream_bytes(sock: socket.socket, size: int) -> bytes:
    return recvall(sock, size)


def make_register_packet(username: str, visible: bool = True, display_name: str | None = None) -> dict:
    return {
        "type": "register",
        "username": username,
        "visible": visible,
        "display_name": display_name or username,
    }


def make_text_packet(sender: str, text: str) -> dict:
    return {
        "type": "text",
        "sender": sender,
        "text": text,
    }


def make_private_packet(sender: str, target: str, text: str) -> dict:
    return {
        "type": "private",
        "sender": sender,
        "target": target,
        "text": text,
    }


def make_system_packet(text: str) -> dict:
    return {
        "type": "system",
        "text": text,
    }


def make_list_packet() -> dict:
    return {
        "type": "list",
    }


def make_user_list_packet(users: list[str]) -> dict:
    return {
        "type": "user_list",
        "users": users,
    }


def make_audio_packet(sender: str, file_path: str) -> dict:
    return {
        "type": "audio_file",
        "sender": sender,
        "filename": os.path.basename(file_path),
        "file_size": os.path.getsize(file_path),
    }


def make_stream_packet(sender: str, target: str, data_size: int) -> dict:
    return {
        "type": "stream",
        "sender": sender,
        "target": target,
        "data_size": data_size,
    }