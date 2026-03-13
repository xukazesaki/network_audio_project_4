import socket
import threading
from config import HOST, PORT, BUFFER_SIZE, ENCODING

# client_id -> {"conn": conn, "addr": addr}
clients = {}
clients_lock = threading.Lock()
next_client_id = 1
server_running = True


def send_to_client(client_id: int, message: str) -> bool:
    """
    给指定 client 发送消息
    成功返回 True，失败返回 False
    """
    with clients_lock:
        client_info = clients.get(client_id)

    if client_info is None:
        return False

    conn = client_info["conn"]
    try:
        conn.sendall(message.encode(ENCODING))
        return True
    except (ConnectionResetError, BrokenPipeError, OSError):
        remove_client(client_id)
        return False


def broadcast(message: str):
    """
    server 向所有在线 client 广播消息
    """
    dead_ids = []

    with clients_lock:
        current_clients = list(clients.items())

    for client_id, info in current_clients:
        conn = info["conn"]
        try:
            conn.sendall(message.encode(ENCODING))
        except (ConnectionResetError, BrokenPipeError, OSError):
            dead_ids.append(client_id)

    for client_id in dead_ids:
        remove_client(client_id)


def remove_client(client_id: int):
    with clients_lock:
        info = clients.pop(client_id, None)

    if info:
        try:
            info["conn"].close()
        except:
            pass
        print(f"[-] client {client_id} 已移除，地址：{info['addr']}")


def list_clients():
    with clients_lock:
        if not clients:
            print("[*] 当前没有在线客户端")
            return

        print("[*] 当前在线客户端：")
        for client_id, info in clients.items():
            print(f"    ID={client_id}, addr={info['addr']}")


def handle_client(client_id: int, conn: socket.socket, addr):
    print(f"[+] client {client_id} 接入：{addr}")

    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                print(f"[-] client {client_id} 断开连接")
                break

            msg = data.decode(ENCODING).strip()
            print(f"[client {client_id} {addr}] {msg}")

            if msg.lower() == "quit":
                print(f"[-] client {client_id} 主动退出")
                break

            # 注意：这里只打印，不转发给其他 client
            # client 之间不会互相看到消息

    except (ConnectionResetError, OSError) as e:
        print(f"[!] client {client_id} 异常断开：{e}")

    finally:
        remove_client(client_id)


def server_input_loop():
    """
    server 控制台命令：
    1. all 消息内容     -> 广播给所有 client
    2. to client_id 内容 -> 发给指定 client
    3. list            -> 查看在线 client
    4. quit            -> 关闭服务器
    """
    global server_running

    print("可用命令：")
    print("  all <消息>            广播给所有客户端")
    print("  to <client_id> <消息> 单独发送给某个客户端")
    print("  list                  查看当前在线客户端")
    print("  quit                  关闭服务器")

    while server_running:
        try:
            cmd = input("server> ").strip()
            if not cmd:
                continue

            if cmd.lower() == "list":
                list_clients()
                continue

            if cmd.lower() == "quit":
                print("[!] 服务器准备关闭")
                broadcast("[SERVER] 服务器即将关闭")
                server_running = False
                break

            if cmd.startswith("all "):
                msg = cmd[4:].strip()
                if msg:
                    broadcast(f"[SERVER][广播] {msg}")
                else:
                    print("[!] 广播消息不能为空")
                continue

            if cmd.startswith("to "):
                parts = cmd.split(" ", 2)
                if len(parts) < 3:
                    print("[!] 格式错误，应为：to <client_id> <消息>")
                    continue

                try:
                    client_id = int(parts[1])
                except ValueError:
                    print("[!] client_id 必须是整数")
                    continue

                msg = parts[2].strip()
                if not msg:
                    print("[!] 私发消息不能为空")
                    continue

                ok = send_to_client(client_id, f"[SERVER][私发] {msg}")
                if not ok:
                    print(f"[!] 发送失败，client {client_id} 不存在或已断开")
                continue

            print("[!] 未知命令")
            print("    可用：all / to / list / quit")

        except EOFError:
            break
        except KeyboardInterrupt:
            print("\n[!] 输入线程结束")
            server_running = False
            break


def main():
    global next_client_id
    global server_running

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(20)

    print(f"服务端监听中：{HOST}:{PORT}")

    input_thread = threading.Thread(target=server_input_loop, daemon=True)
    input_thread.start()

    try:
        while server_running:
            try:
                server_socket.settimeout(1.0)
                conn, addr = server_socket.accept()
            except socket.timeout:
                continue

            with clients_lock:
                client_id = next_client_id
                next_client_id += 1
                clients[client_id] = {"conn": conn, "addr": addr}

            t = threading.Thread(
                target=handle_client,
                args=(client_id, conn, addr),
                daemon=True
            )
            t.start()

    except KeyboardInterrupt:
        print("\n[!] 服务端收到 Ctrl+C，准备退出")

    finally:
        server_running = False

        with clients_lock:
            current_clients = list(clients.items())
            clients.clear()

        for client_id, info in current_clients:
            try:
                info["conn"].close()
            except:
                pass

        server_socket.close()
        print("[*] 服务端已关闭")


if __name__ == "__main__":
    main()