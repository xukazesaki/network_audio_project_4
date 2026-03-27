import socket
import threading

from config import HOST, PORT
from protocol import recv_packet, send_packet


clients = {}  # {username: socket}
clients_lock = threading.Lock()


def _safe_send(username, msg_type, sender, data_dict=None, payload=None) -> bool:
    with clients_lock:
        conn = clients.get(username)

    if conn is None:
        return False

    try:
        send_packet(conn, msg_type, sender, data_dict, payload)
        return True
    except Exception:
        remove_client(username)
        return False


def broadcast_users():
    with clients_lock:
        names = sorted(clients.keys())

    for name in names:
        _safe_send(name, "user_list", "Server", {"users": names})


def remove_client(username):
    if not username:
        return

    with clients_lock:
        conn = clients.pop(username, None)

    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        print(f"[-] 用户断开: {username}")
        broadcast_users()


def handle_client(conn, addr):
    my_name = None
    print(f"[+] 新连接: {addr}")

    try:
        while True:
            header, payload = recv_packet(conn)
            if not header:
                break

            msg_type = header.get("type")
            sender = header.get("sender")
            target = header.get("target")

            if msg_type == "login":
                requested_name = (sender or "").strip()
                if not requested_name:
                    continue

                with clients_lock:
                    old_conn = clients.get(requested_name)
                    if old_conn is not None and old_conn is not conn:
                        try:
                            old_conn.close()
                        except Exception:
                            pass
                    clients[requested_name] = conn

                my_name = requested_name
                print(f"[+] 用户登录: {my_name}")
                broadcast_users()
                continue

            if not my_name:
                continue

            extra = {
                key: value
                for key, value in header.items()
                if key not in {"type", "sender", "payload_len"}
            }

            if target:
                if target == my_name:
                    continue
                _safe_send(target, msg_type, my_name, extra, payload)
                continue

            with clients_lock:
                recipients = [name for name in clients.keys() if name != my_name]

            for username in recipients:
                _safe_send(username, msg_type, my_name, extra, payload)

    finally:
        try:
            conn.close()
        except Exception:
            pass
        remove_client(my_name)


if __name__ == "__main__":
    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)
    print(f"服务器已启动: {HOST}:{PORT}")

    while True:
        client_conn, client_addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(client_conn, client_addr), daemon=True).start()
