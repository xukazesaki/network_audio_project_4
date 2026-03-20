import os
import socket
import threading
import time

from audio_utils import play_wav
from config import HOST, PORT, SERVER_SAVE_DIR, ENCODING
from protocol import (
    recv_file_bytes,
    recv_json,
    send_file_bytes,
    send_json,
    make_system_packet,
    make_text_packet,
    make_audio_packet,
)

# clients:
# client_id -> {
#     "conn": socket对象,
#     "addr": 客户端地址,
#     "username": 用户名
# }
clients = {}

# usernames:
# username -> client_id
usernames = {}

clients_lock = threading.Lock()
next_client_id = 1
server_running = True
last_received_audio = None


def ensure_server_dir():
    """
    确保服务端保存音频的目录存在。
    """
    os.makedirs(SERVER_SAVE_DIR, exist_ok=True)


def list_clients():
    """
    在服务端控制台打印当前在线客户端。
    """
    with clients_lock:
        if not clients:
            print("[*] 当前没有在线客户端")
            return

        print("[*] 当前在线客户端：")
        for client_id, info in clients.items():
            print(f"    ID={client_id}, username={info.get('username')}, addr={info['addr']}")


def remove_client(client_id: int):
    """
    安全移除客户端：
    1. 从 clients 中删掉
    2. 如果有用户名，也从 usernames 中删掉
    3. 关闭连接
    """
    with clients_lock:
        info = clients.pop(client_id, None)
        if info and info.get("username"):
            usernames.pop(info["username"], None)

    if info:
        try:
            info["conn"].close()
        except:
            pass
        print(f"[-] client {client_id} 已移除，地址：{info['addr']}")


def register_client(client_id: int, conn: socket.socket) -> str | None:
    """
    客户端连接后，第一步必须注册用户名。
    如果注册成功，返回用户名。
    如果失败，返回 None。
    """
    meta = recv_json(conn)

    if meta.get("type") != "register":
        send_json(conn, make_system_packet("请先注册用户名"))
        return None

    username = meta.get("username", "").strip()

    if not username:
        send_json(conn, make_system_packet("用户名不能为空"))
        return None

    with clients_lock:
        if username in usernames:
            send_json(conn, make_system_packet(f"用户名 {username} 已存在"))
            return None

        clients[client_id]["username"] = username
        usernames[username] = client_id

    send_json(conn, make_system_packet(f"注册成功，当前用户名：{username}"))
    print(f"[+] client {client_id} 注册用户名：{username}")
    return username


def send_private_text(sender: str, target: str, text: str) -> bool:
    """
    私发文本消息给目标用户。
    成功返回 True，失败返回 False。
    """
    with clients_lock:
        target_id = usernames.get(target)
        if target_id is None:
            return False

        info = clients.get(target_id)
        if info is None:
            return False

        conn = info["conn"]

    try:
        send_json(conn, {
            "type": "private",
            "sender": sender,
            "text": text,
        })
        return True
    except Exception:
        remove_client(target_id)
        return False

def forward_audio_to_user(sender: str, target: str, meta: dict, conn: socket.socket) -> bool:
    """
    把某个客户端上传的音频文件转发给目标客户端。
    这里不会落地保存到服务端，而是直接转发。
    """
    with clients_lock:
        target_id = usernames.get(target)
        if target_id is None:
            return False

        info = clients.get(target_id)
        if info is None:
            return False

        target_conn = info["conn"]

    try:
        # 发给目标客户端的元信息里，不需要 target 字段
        forward_meta = {
            "type": "audio_file",
            "sender": sender,
            "filename": meta["filename"],
            "file_size": meta["file_size"],
        }
        send_json(target_conn, forward_meta)

        remaining = meta["file_size"]
        while remaining > 0:
            chunk = conn.recv(min(4096, remaining))
            if not chunk:
                raise ConnectionError("转发音频时连接断开")
            target_conn.sendall(chunk)
            remaining -= len(chunk)

        return True
    except Exception:
        remove_client(target_id)
        return False

def broadcast_system_message(text: str):
    """
    给所有在线客户端广播系统消息。
    用于服务端关闭等场景。
    """
    with clients_lock:
        all_conns = [info["conn"] for info in clients.values()]

    for conn in all_conns:
        try:
            send_json(conn, make_system_packet(text))
        except:
            pass


def send_text_to_client(target_username: str, text: str) -> bool:
    """
    服务端主动给指定用户发文本。
    """
    with clients_lock:
        target_id = usernames.get(target_username)
        if target_id is None:
            return False

        info = clients.get(target_id)
        if info is None:
            return False

        conn = info["conn"]

    try:
        send_json(conn, make_text_packet("SERVER", text))
        return True
    except Exception:
        remove_client(target_id)
        return False


def send_text_to_all(text: str):
    """
    服务端主动给所有客户端广播文本。
    """
    with clients_lock:
        all_items = list(clients.items())

    for client_id, info in all_items:
        try:
            send_json(info["conn"], make_text_packet("SERVER", text))
        except Exception:
            remove_client(client_id)


def send_audio_to_client(target_username: str, file_path: str) -> bool:
    """
    服务端主动给某个客户端发送音频文件。
    """
    if not os.path.exists(file_path):
        return False

    with clients_lock:
        target_id = usernames.get(target_username)
        if target_id is None:
            return False

        info = clients.get(target_id)
        if info is None:
            return False

        conn = info["conn"]

    try:
        send_json(conn, make_audio_packet("SERVER", file_path))
        send_file_bytes(conn, file_path)
        return True
    except Exception:
        remove_client(target_id)
        return False


def handle_audio_from_client(client_id: int, meta: dict, conn: socket.socket):
    """
    处理客户端发来的音频文件：
    1. 如果带 target，就转发给指定客户端
    2. 如果不带 target，就保存到服务端
    """
    global last_received_audio

    sender = meta.get("sender", "UNKNOWN")
    filename = meta["filename"]
    file_size = meta["file_size"]
    target = meta.get("target")

    # 情况1：客户端私发音频给另一个客户端
    if target:
        print(f"[AUDIO] 收到来自 {sender} 的私发音频，目标：{target}，文件：{filename}")
        ok = forward_audio_to_user(sender, target, meta, conn)

        if ok:
            try:
                send_json(conn, make_system_packet(f"音频已发送给 {target}"))
            except:
                pass
        else:
            try:
                send_json(conn, make_system_packet(f"用户 {target} 不在线或音频转发失败"))
            except:
                pass

            # 目标不存在时，也要把这段音频正文从连接里读掉，否则协议会乱
            remaining = file_size
            while remaining > 0:
                chunk = conn.recv(min(4096, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)

        return

    # 情况2：普通上传给服务端
    ts = time.strftime("%Y%m%d_%H%M%S")
    save_name = f"from_{sender}_{ts}_{filename}"
    save_path = os.path.join(SERVER_SAVE_DIR, save_name)

    print(f"[AUDIO] 收到来自 {sender} 的音频文件：{filename} ({file_size} bytes)")
    recv_file_bytes(conn, save_path, file_size)
    print(f"[AUDIO] 已保存到：{save_path}")

    last_received_audio = save_path

def handle_client(client_id: int, conn: socket.socket, addr):
    """
    每个客户端由一个独立线程处理。
    流程：
    1. 先注册用户名
    2. 再循环接收消息
    """
    print(f"[+] client {client_id} 接入：{addr}")

    username = None

    try:
        username = register_client(client_id, conn)
        if username is None:
            return

        while True:
            meta = recv_json(conn)
            msg_type = meta.get("type")

            if msg_type == "text":
                text = meta.get("text", "")
                print(f"[{username}] {text}")

                if text.lower() == "quit":
                    print(f"[-] {username} 主动退出")
                    break

            elif msg_type == "private":
                sender = meta.get("sender", username)
                target = meta.get("target", "").strip()
                text = meta.get("text", "").strip()

                if not target or not text:
                    send_json(conn, make_system_packet("私发格式错误"))
                    continue

                ok = send_private_text(sender, target, text)
                if not ok:
                    send_json(conn, make_system_packet(f"用户 {target} 不在线或不存在"))
                else:
                    send_json(conn, make_system_packet(f"已发送给 {target}"))

            elif msg_type == "audio_file":
                handle_audio_from_client(client_id, meta, conn)

            elif msg_type == "list":
                with clients_lock:
                    online_users = list(usernames.keys())

                if online_users:
                    send_json(conn, make_system_packet("在线用户：" + ", ".join(online_users)))
                else:
                    send_json(conn, make_system_packet("当前没有在线用户"))

            else:
                print(f"[!] 未知消息类型：{meta}")

    except (ConnectionError, OSError) as e:
        print(f"[!] client {client_id} 异常断开：{e}")

    finally:
        remove_client(client_id)


def server_input_loop(server_socket: socket.socket):
    """
    服务端控制台命令线程。
    可在服务端输入命令进行管理。
    """
    global server_running

    print("\n服务端可用命令：")
    print("  list                         查看在线客户端")
    print("  all <消息>                   向所有客户端广播文本")
    print("  to <用户名> <消息>           向指定用户发送文本")
    print("  sendaudio <用户名> <路径>    向指定用户发送音频文件")
    print("  playlast                     播放最近收到的音频")
    print("  playaudio <路径>             播放指定音频文件")
    print("  quit                         关闭服务器\n")

    while server_running:
        try:
            cmd = input("server> ").strip()
            if not cmd:
                continue

            if cmd == "list":
                list_clients()
                continue

            if cmd.startswith("all "):
                text = cmd[4:].strip()
                if text:
                    send_text_to_all(text)
                continue

            if cmd.startswith("to "):
                parts = cmd.split(" ", 2)
                if len(parts) < 3:
                    print("格式错误，应为：to <用户名> <消息>")
                    continue

                target_username = parts[1].strip()
                text = parts[2].strip()

                ok = send_text_to_client(target_username, text)
                if not ok:
                    print(f"[!] 用户 {target_username} 不在线或不存在")
                continue

            if cmd.startswith("sendaudio "):
                parts = cmd.split(" ", 2)
                if len(parts) < 3:
                    print("格式错误，应为：sendaudio <用户名> <音频路径>")
                    continue

                target_username = parts[1].strip()
                file_path = parts[2].strip()

                ok = send_audio_to_client(target_username, file_path)
                if ok:
                    print(f"[AUDIO] 已发送给 {target_username}：{file_path}")
                else:
                    print(f"[AUDIO] 发送失败，用户不存在或文件不存在")
                continue

            if cmd == "playlast":
                global last_received_audio

                if not last_received_audio:
                    print("[AUDIO] 当前还没有收到任何音频文件")
                    continue

                try:
                    play_wav(last_received_audio)
                    print(f"[AUDIO] 正在播放：{last_received_audio}")
                except Exception as e:
                    print(f"[AUDIO] 播放失败：{e}")
                continue

            if cmd.startswith("playaudio "):
                file_path = cmd[len("playaudio "):].strip()

                if not file_path:
                    print("格式错误，应为：playaudio <路径>")
                    continue

                if not os.path.exists(file_path):
                    print(f"[AUDIO] 文件不存在：{file_path}")
                    continue

                try:
                    play_wav(file_path)
                    print(f"[AUDIO] 正在播放：{file_path}")
                except Exception as e:
                    print(f"[AUDIO] 播放失败：{e}")
                continue

            if cmd == "quit":
                print("[*] 正在关闭服务器...")
                server_running = False
                broadcast_system_message("服务器即将关闭")
                try:
                    server_socket.close()
                except:
                    pass
                break

            print("未知命令")

        except EOFError:
            break
        except Exception as e:
            print(f"[!] 服务端输入线程异常：{e}")


def main():
    """
    服务端主程序入口。
    """
    global next_client_id

    ensure_server_dir()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(20)

    print(f"服务端监听中：{HOST}:{PORT}")

    input_thread = threading.Thread(
        target=server_input_loop,
        args=(server_socket,),
        daemon=True
    )
    input_thread.start()

    try:
        while server_running:
            try:
                conn, addr = server_socket.accept()
            except OSError:
                break

            with clients_lock:
                client_id = next_client_id
                next_client_id += 1
                clients[client_id] = {
                    "conn": conn,
                    "addr": addr,
                    "username": None,
                }

            t = threading.Thread(
                target=handle_client,
                args=(client_id, conn, addr),
                daemon=True
            )
            t.start()

    except KeyboardInterrupt:
        print("\n[*] 服务器被手动中断")

    finally:
        broadcast_system_message("服务器已关闭")

        with clients_lock:
            all_ids = list(clients.keys())

        for client_id in all_ids:
            remove_client(client_id)

        try:
            server_socket.close()
        except:
            pass

        print("服务端已关闭")


if __name__ == "__main__":
    main()