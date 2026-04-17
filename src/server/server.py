import os
import select
import socket
import threading
import time
import wave

from src.core.audio_manager import AudioManager
from src.core.config import CHANNELS, CHUNK, FORMAT, HOST, PORT, RATE, SERVER_RECEIVE_DIR, UDP_PORT
from src.core.protocol import recv_packet, send_packet
from src.server.auth_service import AuthService


clients = {}  # {username: socket}
clients_lock = threading.Lock()
server_running = True
last_received_audio = None
auth_service = AuthService()
UDP_REGISTER_PACKET = b"__udp_register__"
EXPECTED_UDP_AUDIO_BYTES = CHUNK * 2

# 新增：维护当前已加入组播会议的用户
multicast_members = set()
udp_clients = set()
udp_clients_lock = threading.Lock()


# 确保服务端运行前，音频与账户相关的本地目录已经存在。
def ensure_server_dirs():
    os.makedirs(SERVER_RECEIVE_DIR, exist_ok=True)


# 安全地向某个在线用户发送数据包；失败时自动移除断开的连接。
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


# 直接向某个 socket 发送数据，常用于登录/注册阶段的回包。
def send_direct(conn, msg_type, sender, data_dict=None, payload=None) -> bool:
    try:
        send_packet(conn, msg_type, sender, data_dict, payload)
        return True
    except Exception:
        return False


# 将当前在线用户名单广播给所有已登录客户端。
def broadcast_users():
    with clients_lock:
        names = sorted(clients.keys())

    for name in names:
        _safe_send(name, "user_list", "Server", {"users": names})


# 新增：广播当前组播成员列表
def broadcast_multicast_members():
    with clients_lock:
        members = sorted(multicast_members)
        names = sorted(clients.keys())

    for name in names:
        _safe_send(name, "mcast_user_list", "Server", {"users": members})


# 在服务端控制台打印当前在线客户端列表。
def list_clients():
    with clients_lock:
        names = sorted(clients.keys())

    if not names:
        print("[*] 当前没有在线客户端")
        return

    print("[*] 当前在线客户端：")
    for idx, name in enumerate(names, start=1):
        print(f"    {idx}. {name}")


# 移除一个已断开的客户端，并刷新全局在线列表。
def remove_client(username):
    if not username:
        return

    with clients_lock:
        conn = clients.pop(username, None)
        multicast_members.discard(username)

    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        print(f"[-] 用户断开: {username}")
        broadcast_users()
        broadcast_multicast_members()


# 从服务端向所有在线用户发送文本广播。
def send_text_to_all(text: str):
    with clients_lock:
        recipients = list(clients.keys())

    for username in recipients:
        _safe_send(username, "text", "Server", {"msg": text})


# 从服务端向指定用户发送一条文本消息。
def send_text_to_client(target: str, text: str) -> bool:
    return _safe_send(target, "text", "Server", {"msg": text})


# 从服务端向指定用户发送本地音频文件。
def send_audio_to_client(target: str, file_path: str) -> bool:
    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except Exception:
        return False

    return _safe_send(target, "audio", "Server", {}, data)


# 保存最近一次收到的离线音频，方便服务端回放。
def save_incoming_audio(sender: str, payload: bytes):
    global last_received_audio

    if not payload:
        return

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{sender}_{timestamp}.wav"
    path = os.path.join(SERVER_RECEIVE_DIR, filename)

    try:
        audio = AudioManager()
        sample_width = audio.pa.get_sample_size(FORMAT)
        audio.pa.terminate()
    except Exception:
        sample_width = 2

    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_width)
        wf.setframerate(RATE)
        wf.writeframes(payload)

    last_received_audio = path
    print(f"[AUDIO] 已保存来自 {sender} 的音频: {path}")


# 处理注册与登录请求，并向客户端返回对应的认证结果。
def start_udp_audio_relay():
    try:
        relay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        relay_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        relay_sock.bind(("0.0.0.0", UDP_PORT))
        relay_sock.setblocking(False)
    except OSError as e:
        print(f"[!] [UDP] relay failed to start on port {UDP_PORT}: {e}")
        return

    print(f"[*] [UDP] relay started on port: {UDP_PORT}")

    try:
        while server_running:
            ready, _, _ = select.select([relay_sock], [], [], 0.5)
            if not ready:
                continue

            try:
                data, addr = relay_sock.recvfrom(8192)
            except BlockingIOError:
                continue

            if not data:
                continue

            with udp_clients_lock:
                if addr not in udp_clients:
                    udp_clients.add(addr)
                    print(f"[UDP] new audio source: {addr}")
                recipients = [client_addr for client_addr in udp_clients if client_addr != addr]

            if data == UDP_REGISTER_PACKET:
                continue

            if len(data) != EXPECTED_UDP_AUDIO_BYTES:
                continue

            stale_clients = []
            for client_addr in recipients:
                try:
                    relay_sock.sendto(data, client_addr)
                except Exception:
                    stale_clients.append(client_addr)

            if stale_clients:
                with udp_clients_lock:
                    for client_addr in stale_clients:
                        udp_clients.discard(client_addr)
    finally:
        with udp_clients_lock:
            udp_clients.clear()
        relay_sock.close()


def handle_auth_message(conn, msg_type, sender, current_user=None):
    requested_name = (sender or "").strip()

    if current_user:
        send_direct(conn, f"{msg_type}_error", "Server", {"code": "already_authenticated", "username": current_user})
        send_direct(conn, "text", "Server", {"msg": f"当前连接已经登录为 {current_user}，不能再次认证"})
        return None

    if msg_type == "register":
        ok, code, user = auth_service.register(requested_name)
        if not ok:
            send_direct(conn, "register_error", "Server", {"code": code, "username": requested_name})
            send_direct(conn, "text", "Server", {"msg": f"注册失败: {code}"})
            return None

        username = user["username"]
        send_direct(conn, "register_ok", "Server", {"username": username, "nickname": user["nickname"]})
        send_direct(conn, "text", "Server", {"msg": f"注册成功: {username}"})
        print(f"[AUTH] 用户注册: {username}")
        return None

    if msg_type == "login":
        ok, code, user = auth_service.login(requested_name)
        if not ok:
            send_direct(conn, "login_error", "Server", {"code": code, "username": requested_name})
            send_direct(conn, "text", "Server", {"msg": f"登录失败: {code}"})
            return None

        username = user["username"]
        with clients_lock:
            old_conn = clients.get(username)
            if old_conn is not None and old_conn is not conn:
                try:
                    send_packet(old_conn, "text", "Server", {"msg": "你的账号在其他地方登录，当前连接已断开"})
                    old_conn.close()
                except Exception:
                    pass
            clients[username] = conn

        send_direct(conn, "login_ok", "Server", {"username": username, "nickname": user["nickname"]})
        print(f"[AUTH] 用户登录: {username}")
        broadcast_users()
        broadcast_multicast_members()

        return username

    return None


# 处理单个客户端连接，包括认证、消息收发与转发逻辑。
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

            if msg_type in {"register", "login"}:
                auth_name = handle_auth_message(conn, msg_type, sender, my_name)
                if auth_name:
                    my_name = auth_name
                continue

            if not my_name:
                send_direct(conn, "text", "Server", {"msg": "请先注册或登录"})
                continue

            # 新增：处理组播成员加入
            if msg_type == "mcast_join":
                with clients_lock:
                    multicast_members.add(my_name)
                print(f"[MCAST] {my_name} 加入组播会议")
                broadcast_multicast_members()
                continue

            # 新增：处理组播成员退出
            if msg_type == "mcast_leave":
                with clients_lock:
                    multicast_members.discard(my_name)
                print(f"[MCAST] {my_name} 退出组播会议")
                broadcast_multicast_members()
                continue

            extra = {
                key: value
                for key, value in header.items()
                if key not in {"type", "sender", "payload_len"}
            }

            if msg_type == "text":
                text = header.get("msg", "")
                print(f"[TEXT] {my_name} -> {target or 'ALL'}: {text}")
            elif msg_type == "audio":
                print(f"[AUDIO] {my_name} -> {target or 'ALL'}: {len(payload)} bytes")
                save_incoming_audio(my_name, payload)
            elif msg_type == "file":
                print(f"[FILE] {my_name} -> {target or 'ALL'}: {header.get('filename', 'unknown')}")
            elif msg_type == "stream":
                pass

            if target:
                if target == my_name:
                    continue
                ok = _safe_send(target, msg_type, my_name, extra, payload)
                if not ok and msg_type != "stream":
                    _safe_send(my_name, "text", "Server", {"msg": f"用户 {target} 不在线或不存在"})
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


# 打印服务端控制台支持的命令列表。
def print_help():
    print("\n服务端可用命令：")
    print("  help                         查看命令")
    print("  list                         查看在线客户端")
    print("  all <消息>                   向所有客户端广播文本")
    print("  to <用户名> <消息>           向指定用户发送文本")
    print("  sendaudio <用户名> <路径>    向指定用户发送音频文件")
    print("  playlast                     播放最近收到的音频")
    print("  playaudio <路径>             播放指定音频文件")
    print("  quit                         关闭服务器\n")


# 运行服务端控制台输入循环，处理管理员命令。
def server_input_loop(server_socket: socket.socket):
    global server_running

    try:
        audio = AudioManager()
    except Exception:
        audio = None

    print_help()

    while server_running:
        try:
            cmd = input("server> ").strip()
            if not cmd:
                continue

            if cmd == "help":
                print_help()
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

                target = parts[1].strip()
                text = parts[2].strip()
                ok = send_text_to_client(target, text)
                if not ok:
                    print(f"[!] 用户 {target} 不在线或不存在")
                continue

            if cmd.startswith("sendaudio "):
                parts = cmd.split(" ", 2)
                if len(parts) < 3:
                    print("格式错误，应为：sendaudio <用户名> <音频路径>")
                    continue

                target = parts[1].strip()
                file_path = parts[2].strip()
                ok = send_audio_to_client(target, file_path)
                if ok:
                    print(f"[AUDIO] 已发送给 {target}: {file_path}")
                else:
                    print("[AUDIO] 发送失败，用户不存在或文件不存在")
                continue

            if cmd == "playlast":
                if not last_received_audio:
                    print("[AUDIO] 当前还没有收到任何音频")
                    continue
                if audio is None:
                    print("[AUDIO] 当前环境无法播放，请先安装 pyaudio")
                    continue

                try:
                    audio.play_audio(_read_wave_as_pcm(last_received_audio))
                    print(f"[AUDIO] 正在播放: {last_received_audio}")
                except Exception as e:
                    print(f"[AUDIO] 播放失败: {e}")
                continue

            if cmd.startswith("playaudio "):
                file_path = cmd[len("playaudio "):].strip()
                if not file_path:
                    print("格式错误，应为：playaudio <路径>")
                    continue
                if not os.path.exists(file_path):
                    print(f"[AUDIO] 文件不存在: {file_path}")
                    continue
                if audio is None:
                    print("[AUDIO] 当前环境无法播放，请先安装 pyaudio")
                    continue

                try:
                    audio.play_audio(_read_wave_as_pcm(file_path))
                    print(f"[AUDIO] 正在播放: {file_path}")
                except Exception as e:
                    print(f"[AUDIO] 播放失败: {e}")
                continue

            if cmd == "quit":
                print("[*] 正在关闭服务器...")
                server_running = False
                send_text_to_all("服务器即将关闭")
                try:
                    server_socket.close()
                except Exception:
                    pass
                break

            print("未知命令，输入 help 查看可用命令")

        except EOFError:
            break
        except Exception as e:
            print(f"[!] 服务端输入线程异常: {e}")

    if audio is not None:
        try:
            audio.pa.terminate()
        except Exception:
            pass


# 读取 wav 文件内容并返回原始 PCM 数据，用于服务端播放。
def _read_wave_as_pcm(file_path: str) -> bytes:
    with wave.open(file_path, "rb") as wf:
        return wf.readframes(wf.getnframes())


if __name__ == "__main__":
    ensure_server_dirs()

    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)
    print(f"服务器已启动: {HOST}:{PORT}")

    udp_thread = threading.Thread(target=start_udp_audio_relay, daemon=True)
    udp_thread.start()

    input_thread = threading.Thread(target=server_input_loop, args=(server_socket,), daemon=True)
    input_thread.start()

    try:
        while server_running:
            try:
                client_conn, client_addr = server_socket.accept()
            except OSError:
                break
            threading.Thread(target=handle_client, args=(client_conn, client_addr), daemon=True).start()
    finally:
        with clients_lock:
            names = list(clients.keys())

        for username in names:
            remove_client(username)

        try:
            server_socket.close()
        except Exception:
            pass

        print("服务端已关闭")
