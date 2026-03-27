# server.py

import os
import socket
import threading
import time

from audio_core import AudioCore
from config import HOST, PORT, SERVER_SAVE_DIR
from protocol import (
    recv_file_bytes,
    recv_json,
    recv_stream_bytes,
    send_bytes,
    send_file_bytes,
    send_json,
    make_audio_packet,
    make_system_packet,
    make_text_packet,
    make_stream_packet,
    make_user_list_packet,
)

clients = {}
usernames = {}
clients_lock = threading.Lock()

next_client_id = 1
server_running = True
last_received_audio = None


def ensure_server_dir():
    os.makedirs(SERVER_SAVE_DIR, exist_ok=True)


def _make_client_info(conn: socket.socket, addr):
    return {
        "conn": conn,
        "addr": addr,
        "username": None,
        "display_name": None,
        "visible": True,
        "send_lock": threading.Lock(),
    }


def get_visible_usernames():
    with clients_lock:
        result = [
            info["display_name"]
            for info in clients.values()
            if info.get("username") and info.get("visible", True)
        ]
    return sorted(result)


def broadcast_user_list():
    packet = make_user_list_packet(get_visible_usernames())

    with clients_lock:
        all_ids = list(clients.keys())

    for client_id in all_ids:
        safe_send_json_to_client(client_id, packet)


def safe_send_json_to_client(client_id: int, obj: dict) -> bool:
    with clients_lock:
        info = clients.get(client_id)
    if info is None:
        return False

    try:
        with info["send_lock"]:
            send_json(info["conn"], obj)
        return True
    except Exception:
        remove_client(client_id)
        return False


def safe_send_stream_to_client(client_id: int, header: dict, payload: bytes) -> bool:
    with clients_lock:
        info = clients.get(client_id)
    if info is None:
        return False

    try:
        with info["send_lock"]:
            send_json(info["conn"], header)
            send_bytes(info["conn"], payload)
        return True
    except Exception:
        remove_client(client_id)
        return False


def safe_send_file_to_client(client_id: int, header: dict, file_path: str) -> bool:
    with clients_lock:
        info = clients.get(client_id)
    if info is None:
        return False

    try:
        with info["send_lock"]:
            send_json(info["conn"], header)
            send_file_bytes(info["conn"], file_path)
        return True
    except Exception:
        remove_client(client_id)
        return False


def list_clients():
    with clients_lock:
        if not clients:
            print("[*] 当前没有在线客户端")
            return

        print("[*] 当前在线客户端：")
        for client_id, info in clients.items():
            print(
                f"    ID={client_id}, "
                f"username={info.get('username')}, "
                f"display_name={info.get('display_name')}, "
                f"visible={info.get('visible')}, "
                f"addr={info['addr']}"
            )


def remove_client(client_id: int):
    removed = False
    with clients_lock:
        info = clients.pop(client_id, None)
        if info and info.get("username"):
            usernames.pop(info["username"], None)
            removed = True

    if info:
        try:
            info["conn"].close()
        except Exception:
            pass
        print(f"[-] client {client_id} 已移除，地址：{info['addr']}")

    if removed:
        broadcast_user_list()


def register_client(client_id: int, conn: socket.socket):
    while True:
        meta = recv_json(conn)

        if meta.get("type") != "register":
            safe_send_json_to_client(client_id, make_system_packet("请先注册用户名"))
            continue

        username = meta.get("username", "").strip()
        visible = bool(meta.get("visible", True))
        display_name = meta.get("display_name", "").strip() or username

        if not username:
            safe_send_json_to_client(client_id, make_system_packet("用户名不能为空"))
            continue

        with clients_lock:
            if username in usernames:
                pass
            else:
                clients[client_id]["username"] = username
                clients[client_id]["display_name"] = display_name
                clients[client_id]["visible"] = visible
                usernames[username] = client_id
                print(
                    f"[+] client {client_id} 注册："
                    f"username={username}, display_name={display_name}, visible={visible}"
                )
                break

        safe_send_json_to_client(client_id, make_system_packet(f"用户名 {username} 已存在，请换一个"))

    safe_send_json_to_client(client_id, make_system_packet(f"注册成功，当前用户名：{display_name}"))
    broadcast_user_list()
    return username


def broadcast_system_message(text: str):
    with clients_lock:
        all_ids = list(clients.keys())

    for client_id in all_ids:
        safe_send_json_to_client(client_id, make_system_packet(text))


def send_private_text(sender: str, target: str, text: str) -> bool:
    target_id = None
    with clients_lock:
        for cid, info in clients.items():
            if info.get("visible", True) and info.get("display_name") == target:
                target_id = cid
                break

    if target_id is None:
        return False

    return safe_send_json_to_client(
        target_id,
        {
            "type": "private",
            "sender": sender,
            "text": text,
        }
    )


def send_text_to_client(target_username: str, text: str) -> bool:
    target_id = None
    with clients_lock:
        for cid, info in clients.items():
            if info.get("visible", True) and info.get("display_name") == target_username:
                target_id = cid
                break

    if target_id is None:
        return False

    return safe_send_json_to_client(target_id, make_text_packet("SERVER", text))


def send_text_to_all(text: str):
    with clients_lock:
        all_ids = list(clients.keys())

    for client_id in all_ids:
        safe_send_json_to_client(client_id, make_text_packet("SERVER", text))


def send_audio_to_client(target_username: str, file_path: str) -> bool:
    if not os.path.exists(file_path):
        return False

    target_id = None
    with clients_lock:
        for cid, info in clients.items():
            if info.get("visible", True) and info.get("display_name") == target_username:
                target_id = cid
                break

    if target_id is None:
        return False

    return safe_send_file_to_client(
        target_id,
        make_audio_packet("SERVER", file_path),
        file_path
    )


def handle_audio_from_client(meta: dict, conn: socket.socket):
    global last_received_audio

    sender = meta.get("sender", "UNKNOWN")
    filename = meta["filename"]
    file_size = int(meta["file_size"])

    ts = time.strftime("%Y%m%d_%H%M%S")
    save_name = f"from_{sender}_{ts}_{filename}"
    save_path = os.path.join(SERVER_SAVE_DIR, save_name)

    print(f"[AUDIO] 收到来自 {sender} 的音频文件：{filename} ({file_size} bytes)")
    recv_file_bytes(conn, save_path, file_size)
    print(f"[AUDIO] 已保存到：{save_path}")

    last_received_audio = save_path


def forward_stream_to_target(sender_client_id: int, target_name: str, audio_bytes: bytes) -> bool:
    target_id = None
    sender_display_name = None

    with clients_lock:
        sender_info = clients.get(sender_client_id)
        if sender_info is None:
            return False
        sender_display_name = sender_info.get("display_name") or sender_info.get("username")

        for cid, info in clients.items():
            if info.get("visible", True) and info.get("display_name") == target_name:
                target_id = cid
                break

    if target_id is None:
        return False

    if target_id == sender_client_id:
        return False

    header = make_stream_packet(sender_display_name, target_name, len(audio_bytes))
    return safe_send_stream_to_client(target_id, header, audio_bytes)


def handle_client(client_id: int, conn: socket.socket, addr):
    print(f"[+] client {client_id} 接入：{addr}")
    username = None

    try:
        username = register_client(client_id, conn)

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
                    safe_send_json_to_client(client_id, make_system_packet("私发格式错误"))
                    continue

                ok = send_private_text(sender, target, text)
                if not ok:
                    safe_send_json_to_client(client_id, make_system_packet(f"用户 {target} 不在线或不存在"))
                else:
                    safe_send_json_to_client(client_id, make_system_packet(f"已发送给 {target}"))

            elif msg_type == "audio_file":
                handle_audio_from_client(meta, conn)

            elif msg_type == "stream":
                target = meta.get("target", "").strip()
                data_size = int(meta.get("data_size", 0))

                if not target:
                    safe_send_json_to_client(client_id, make_system_packet("实时语音必须指定目标用户"))
                    continue

                if data_size <= 0:
                    safe_send_json_to_client(client_id, make_system_packet("无效的实时音频包"))
                    continue

                audio_bytes = recv_stream_bytes(conn, data_size)
                ok = forward_stream_to_target(client_id, target, audio_bytes)

                if not ok:
                    safe_send_json_to_client(client_id, make_system_packet(f"实时语音目标 {target} 不在线、无效或不能是自己"))

            elif msg_type == "list":
                safe_send_json_to_client(client_id, make_user_list_packet(get_visible_usernames()))

            else:
                print(f"[!] 未知消息类型：{meta}")

    except (ConnectionError, OSError) as e:
        print(f"[!] client {client_id} 异常断开：{e}")

    finally:
        remove_client(client_id)


def server_input_loop(server_socket: socket.socket):
    global server_running
    audio = None

    print("\n服务端可用命令：")
    print("  list                         查看在线客户端")
    print("  all <消息>                   向所有客户端广播文本")
    print("  to <用户名> <消息>           向指定用户发送文本")
    print("  sendaudio <用户名> <路径>    向指定用户发送音频文件")
    print("  playlast                     播放最近收到的音频")
    print("  playaudio <路径>             播放指定音频文件")
    print("  quit                         关闭服务器\n")

    try:
        audio = AudioCore()
    except Exception:
        audio = None

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
                    print("[AUDIO] 发送失败，用户不存在或文件不存在")
                continue

            if cmd == "playlast":
                if not last_received_audio:
                    print("[AUDIO] 当前还没有收到任何音频文件")
                    continue
                if audio is None:
                    print("[AUDIO] 当前环境无法播放，请先安装 pyaudio")
                    continue

                try:
                    audio.play_wav(last_received_audio)
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
                if audio is None:
                    print("[AUDIO] 当前环境无法播放，请先安装 pyaudio")
                    continue

                try:
                    audio.play_wav(file_path)
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
                except Exception:
                    pass
                break

            print("未知命令")

        except EOFError:
            break
        except Exception as e:
            print(f"[!] 服务端输入线程异常：{e}")

    if audio is not None:
        audio.terminate()


def main():
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
                clients[client_id] = _make_client_info(conn, addr)

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
        except Exception:
            pass

        print("服务端已关闭")


if __name__ == "__main__":
    main()