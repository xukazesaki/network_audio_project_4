import json
import socket
import struct


HEADER_STRUCT = struct.Struct("!I")


# 从 socket 中精确读取指定字节数的数据。
def recvall(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Connection closed while receiving data")
        data.extend(chunk)
    return bytes(data)


def send_packet(sock, msg_type, sender, data_dict=None, binary_payload=None):
    """
    Send a packet with a JSON header and an optional binary payload.
    """
    header = {
        "type": msg_type,
        "sender": sender,
    }
    if data_dict:
        header.update(data_dict)

    payload = binary_payload or b""
    header["payload_len"] = len(payload)
    header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")

    sock.sendall(HEADER_STRUCT.pack(len(header_bytes)))
    sock.sendall(header_bytes)
    if payload:
        sock.sendall(payload)


# 读取并解析一个完整数据包，返回包头和可选的二进制载荷。
def recv_packet(sock):
    """
    Receive a packet and return (header_dict, binary_payload).
    """
    try:
        raw_header_len = recvall(sock, HEADER_STRUCT.size)
        header_len = HEADER_STRUCT.unpack(raw_header_len)[0]
        header_bytes = recvall(sock, header_len)
        header = json.loads(header_bytes.decode("utf-8"))

        payload_len = int(header.get("payload_len", 0))
        payload = recvall(sock, payload_len) if payload_len > 0 else b""
        return header, payload
    except Exception as e:
        print(f"接收异常: {e}")
        return None, None
