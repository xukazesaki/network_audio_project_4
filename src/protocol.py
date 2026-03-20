import json
import os
import socket
import struct


# =========================
# 底层发送 / 接收工具
# =========================

def recvall(sock: socket.socket, size: int) -> bytes:
    """
    从 socket 中精确接收 size 个字节。
    如果连接中途中断，就抛出 ConnectionError。
    """
    data = b""
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            raise ConnectionError("连接已断开")
        data += packet
    return data


def send_json(sock: socket.socket, obj: dict):
    """
    发送一个 JSON 对象。
    协议格式：
    [4字节长度][JSON正文]
    """
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)))
    sock.sendall(raw)


def recv_json(sock: socket.socket) -> dict:
    """
    接收一个 JSON 对象。
    先读4字节长度，再读对应长度的 JSON 正文。
    """
    header = recvall(sock, 4)
    msg_len = struct.unpack("!I", header)[0]
    raw = recvall(sock, msg_len)
    return json.loads(raw.decode("utf-8"))


def send_file_bytes(sock: socket.socket, file_path: str):
    """
    将文件内容按二进制发送出去。
    这里只负责发文件正文，不负责发元信息。
    """
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            sock.sendall(chunk)


def recv_file_bytes(sock: socket.socket, save_path: str, file_size: int):
    """
    接收固定大小的文件内容并保存到 save_path。
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    remaining = file_size
    with open(save_path, "wb") as f:
        while remaining > 0:
            chunk = sock.recv(min(4096, remaining))
            if not chunk:
                raise ConnectionError("接收文件时连接断开")
            f.write(chunk)
            remaining -= len(chunk)


# =========================
# 各类消息构造函数
# =========================

def make_text_packet(sender: str, text: str) -> dict:
    """
    普通文本消息。
    """
    return {
        "type": "text",
        "sender": sender,
        "text": text,
    }


def make_audio_packet(sender: str, file_path: str,target=None) -> dict:
    """
    音频文件消息。
    这里只发送元信息，真正文件内容后续再发。
    """
    packet = {
        "type": "audio_file",
        "sender": sender,
        "filename": os.path.basename(file_path),
        "file_size": os.path.getsize(file_path),
    }

    if target:
        packet["target"] = target

    return packet

def make_register_packet(username: str) -> dict:
    """
    用户注册消息。
    客户端连接成功后，第一条消息应该就是它。
    """
    return {
        "type": "register",
        "username": username,
    }


def make_private_packet(sender: str, target: str, text: str) -> dict:
    """
    私发消息。
    sender: 发送者用户名
    target: 目标用户名
    text: 消息内容
    """
    return {
        "type": "private",
        "sender": sender,
        "target": target,
        "text": text,
    }


def make_system_packet(text: str) -> dict:
    """
    系统消息。
    例如注册成功、用户名已存在、目标用户不在线等。
    """
    return {
        "type": "system",
        "text": text,
    }


def make_list_packet() -> dict:
    """
    请求在线用户列表。
    """
    return {
        "type": "list",
    }