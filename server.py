# server.py
import socket
import threading
from protocol import recv_packet, send_packet
from config import HOST, PORT

clients = {} 
clients_lock = threading.Lock()

def handle_client(conn, addr, client_id):
    print(f"[+] 客户端 {client_id} 已连接: {addr}")
    try:
        while True:
            header, payload = recv_packet(conn)
            if not header:
                break
            
            # 这里的 header 现在包含了 type ('text' 或 'stream')
            # 广播逻辑：转发给除发送者之外的所有人
            with clients_lock:
                target_clients = list(clients.items())
            
            for cid, c_info in target_clients:
                if cid != client_id:
                    try:
                        # 直接原样转发 header 和 payload
                        send_packet(c_info["conn"], header['type'], header['sender'], 
                                    data_dict=header, binary_payload=payload)
                    except:
                        continue
    except Exception as e:
        print(f"[!] 客户端 {client_id} 运行异常: {e}")
    finally:
        with clients_lock:
            clients.pop(client_id, None)
        conn.close()
        print(f"[-] 客户端 {client_id} 断开连接")

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    print(f"[*] 【计网实践】实时音频服务器已启动: {HOST}:{PORT}")
    
    next_id = 1
    try:
        while True:
            conn, addr = server.accept()
            with clients_lock:
                clients[next_id] = {"conn": conn, "addr": addr}
                cid = next_id
                next_id += 1
            threading.Thread(target=handle_client, args=(conn, addr, cid), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[*] 服务器关闭中...")
    finally:
        server.close()

if __name__ == "__main__":
    main()