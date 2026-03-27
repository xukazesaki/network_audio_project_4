import socket
import threading
from protocol import recv_packet, send_packet
from config import HOST, PORT

clients = {} # {用户名: socket}
lock = threading.Lock()

def broadcast_users():
    names = list(clients.keys())
    for name in clients:
        try: send_packet(clients[name], "user_list", "Server", {"users": names})
        except: pass

def handle_client(conn, addr):
    my_name = None
    try:
        while True:
            header, payload = recv_packet(conn)
            if not header: break
            
            h_type = header.get('type')
            sender = header.get('sender')
            target = header.get('target')

            if h_type == 'login':
                my_name = sender
                with lock: clients[my_name] = conn
                broadcast_users()
            elif target in clients: # 定向私发 (任务 4 关键)
                send_packet(clients[target], h_type, sender, header, payload)
            else: # 没选目标就广播
                for name in clients:
                    if name != my_name:
                        send_packet(clients[name], h_type, sender, header, payload)
    finally:
        with lock: 
            if my_name in clients: del clients[my_name]
        conn.close()
        broadcast_users()

if __name__ == "__main__":
    s = socket.socket(); s.bind((HOST, PORT)); s.listen(10)
    print(f"服务器已启动...")
    while True:
        c, a = s.accept()
        threading.Thread(target=handle_client, args=(c, a)).start()