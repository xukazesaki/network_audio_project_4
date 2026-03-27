# protocol.py
import json
import struct
import socket
# !I 表示 4 字节无符号整数（大端序），用于包头长度
HEADER_STRUCT = struct.Struct("!I")

def send_packet(sock, msg_type, sender, data_dict=None, binary_payload=None):
    """
    通用发送函数
    msg_type: "text", "audio_file", "stream"
    binary_payload: 仅在流式传输或发文件时使用的原始字节
    """
    header = {
        "type": msg_type,
        "sender": sender,
        "payload_len": len(binary_payload) if binary_payload else 0
    }
    if data_dict:
        header.update(data_dict)
    
    header_bytes = json.dumps(header).encode('utf-8')
    # 发送：[4字节header长度] + [header内容] + [原始二进制数据]
    sock.sendall(HEADER_STRUCT.pack(len(header_bytes)) + header_bytes)
    if binary_payload:
        sock.sendall(binary_payload)

def recv_packet(sock):
    """
    通用接收函数，返回 (header_dict, binary_payload)
    """
    try:
        raw_header_len = sock.recv(HEADER_STRUCT.size)
        if not raw_header_len: return None, None
        
        header_len = HEADER_STRUCT.unpack(raw_header_len)[0]
        header_bytes = sock.recv(header_len)
        header = json.loads(header_bytes.decode('utf-8'))
        
        payload = b""
        if header.get("payload_len", 0) > 0:
            remaining = header["payload_len"]
            while remaining > 0:
                chunk = sock.recv(min(remaining, 4096))
                if not chunk: break
                payload += chunk
                remaining -= len(chunk)
        return header, payload
    except Exception as e:
        print(f"接收异常: {e}")
        return None, None