# client_cli.py

import os
import socket
import subprocess
import sys
import threading

from audio_core import AudioCore
from config import CLIENT_RECEIVE_DIR, RECORDED_DIR, HOST, PORT
from protocol import (
    make_audio_packet,
    make_list_packet,
    make_private_packet,
    make_register_packet,
    make_text_packet,
    recv_file_bytes,
    recv_json,
    recv_stream_bytes,
    send_file_bytes,
    send_json,
)

running = True
current_record_file = None
username = None
rt_gui_process = None


def ensure_dirs():
    os.makedirs(CLIENT_RECEIVE_DIR, exist_ok=True)
    os.makedirs(RECORDED_DIR, exist_ok=True)


def get_next_record_file():
    ensure_dirs()
    max_index = 0
    for name in os.listdir(RECORDED_DIR):
        if not name.lower().endswith(".wav"):
            continue
        base = os.path.splitext(name)[0]
        if not base.startswith("record"):
            continue
        num_part = base[6:]
        if num_part.isdigit():
            max_index = max(max_index, int(num_part))
    return os.path.join(RECORDED_DIR, f"record{max_index + 1}.wav")


def print_help():
    print("\n可用命令：")
    print("  msg <消息>                 发送文本")
    print("  pm <显示名> <消息>         私发")
    print("  list                       查看在线用户")
    print("  record                     录制 5 秒音频")
    print("  sendaudio                  发送最近一次录音")
    print("  sendaudio <路径>           发送指定音频文件")
    print("  playlocal                  播放最近一次录音")
    print("  playlocal <路径>           播放指定本地音频")
    print("  rtstart <目标显示名>       启动实时语音 GUI")
    print("  rtstop                     关闭实时语音 GUI")
    print("  help                       查看命令")
    print("  quit                       退出客户端")


def send_audio(sock: socket.socket, file_path: str):
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        return

    send_json(sock, make_audio_packet(username, file_path))
    send_file_bytes(sock, file_path)
    print(f"音频发送完成：{file_path}")


def register_username(sock: socket.socket):
    global username

    while True:
        username = input("请输入用户名：").strip()
        if not username:
            print("用户名不能为空")
            continue

        send_json(sock, make_register_packet(username, visible=True, display_name=username))
        meta = recv_json(sock)

        if meta.get("type") == "system":
            text = meta.get("text", "")
            print(text)
            if "注册成功" in text:
                break
        else:
            print("注册响应异常，请重试")


def receive_loop(sock: socket.socket, audio: AudioCore):
    global running

    while running:
        try:
            meta = recv_json(sock)
            msg_type = meta.get("type")

            if msg_type == "text":
                sender = meta.get("sender", "UNKNOWN")
                text = meta.get("text", "")
                print(f"\n[{sender}] {text}")

            elif msg_type == "private":
                sender = meta.get("sender", "UNKNOWN")
                text = meta.get("text", "")
                print(f"\n[私信][{sender}] {text}")

            elif msg_type == "system":
                text = meta.get("text", "")
                print(f"\n[系统] {text}")

            elif msg_type == "user_list":
                users = meta.get("users", [])
                print(f"\n[在线用户] {', '.join(users) if users else '无'}")

            elif msg_type == "audio_file":
                sender = meta.get("sender", "UNKNOWN")
                filename = meta["filename"]
                file_size = int(meta["file_size"])

                save_name = f"from_{sender}_{filename}"
                save_path = os.path.join(CLIENT_RECEIVE_DIR, save_name)

                print(f"\n收到来自 {sender} 的音频文件：{filename} ({file_size} bytes)")
                recv_file_bytes(sock, save_path, file_size)
                print(f"已保存到：{save_path}")

                try:
                    audio.play_wav(save_path)
                except Exception as e:
                    print(f"播放失败：{e}")

            elif msg_type == "stream":
                data_size = int(meta.get("data_size", 0))
                if data_size <= 0:
                    continue

                audio_bytes = recv_stream_bytes(sock, data_size)

                try:
                    audio.play_audio_bytes(audio_bytes)
                except Exception as e:
                    print(f"实时语音播放失败：{e}")

            else:
                print(f"\n收到未知类型消息：{meta}")

        except (ConnectionError, OSError):
            print("\n[!] 与服务端连接已断开")
            running = False
            break
        except Exception as e:
            print(f"\n[!] 接收线程异常：{e}")
            running = False
            break


def _find_gui_script():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ("client_stream_gui.py", "client_stream_gui.pyw"):
        path = os.path.join(base_dir, name)
        if os.path.exists(path):
            return path
    return None


def _pick_python_for_gui():
    python_exec = sys.executable
    if os.name == "nt":
        exe_name = os.path.basename(python_exec).lower()
        if exe_name == "python.exe":
            pythonw_path = os.path.join(os.path.dirname(python_exec), "pythonw.exe")
            if os.path.exists(pythonw_path):
                return pythonw_path
    return python_exec


def start_rt_gui(target_display_name: str):
    global rt_gui_process

    if not target_display_name:
        print("格式错误，应为：rtstart <目标显示名>")
        return

    if target_display_name == username:
        print("实时语音目标不能是自己")
        return

    if rt_gui_process is not None and rt_gui_process.poll() is None:
        print("实时语音 GUI 已经在运行")
        return

    script_path = _find_gui_script()
    if not script_path:
        print("找不到 client_stream_gui.py 或 client_stream_gui.pyw")
        return

    python_exec = _pick_python_for_gui()

    env = os.environ.copy()
    env["RT_GUI_USERNAME"] = f"{username}_rt"
    env["RT_GUI_TARGET"] = target_display_name
    env["RT_GUI_VISIBLE"] = "0"
    env["RT_GUI_DISPLAY_NAME"] = f"{username}_rt"

    kwargs = {
        "cwd": os.path.dirname(script_path),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
        "close_fds": True,
    }

    if os.name == "nt":
        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        kwargs["creationflags"] = creationflags

    try:
        rt_gui_process = subprocess.Popen(
            [python_exec, script_path],
            **kwargs
        )
        print(f"[实时语音 GUI] 已启动，目标用户：{target_display_name}")
    except Exception as e:
        print(f"[实时语音 GUI] 启动失败：{e}")
        rt_gui_process = None


def stop_rt_gui():
    global rt_gui_process

    if rt_gui_process is None or rt_gui_process.poll() is not None:
        rt_gui_process = None
        print("实时语音 GUI 当前没有运行")
        return

    try:
        rt_gui_process.terminate()
        rt_gui_process.wait(timeout=2)
        print("[实时语音 GUI] 已关闭")
    except Exception:
        try:
            rt_gui_process.kill()
            print("[实时语音 GUI] 已强制关闭")
        except Exception as e:
            print(f"[实时语音 GUI] 关闭失败：{e}")
    finally:
        rt_gui_process = None


def main():
    global running, current_record_file

    ensure_dirs()

    audio = AudioCore()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    register_username(sock)

    print(f"已连接到服务端 {HOST}:{PORT}")
    print(f"当前用户名：{username}")
    print_help()

    recv_thread = threading.Thread(target=receive_loop, args=(sock, audio), daemon=True)
    recv_thread.start()

    try:
        while running:
            cmd = input("client> ").strip()
            if not cmd:
                continue

            if cmd == "help":
                print_help()
                continue

            if cmd == "list":
                send_json(sock, make_list_packet())
                continue

            if cmd.startswith("pm "):
                parts = cmd.split(" ", 2)
                if len(parts) < 3:
                    print("格式错误，应为：pm <显示名> <消息>")
                    continue
                target = parts[1].strip()
                text = parts[2].strip()
                if not target or not text:
                    print("目标显示名和消息不能为空")
                    continue
                send_json(sock, make_private_packet(username, target, text))
                continue

            if cmd.startswith("msg "):
                text = cmd[4:].strip()
                if not text:
                    print("消息不能为空")
                    continue
                send_json(sock, make_text_packet(username, text))
                continue

            if cmd == "record":
                try:
                    current_record_file = get_next_record_file()
                    data = audio.record_audio(5)
                    audio.save_wav(current_record_file, data)
                    print(f"录音已保存到：{current_record_file}")
                except Exception as e:
                    print(f"录音失败：{e}")
                continue

            if cmd == "sendaudio":
                if not current_record_file:
                    print("当前还没有录音，请先执行 record")
                    continue
                try:
                    send_audio(sock, current_record_file)
                except Exception as e:
                    print(f"发送失败：{e}")
                continue

            if cmd.startswith("sendaudio "):
                path = cmd[len("sendaudio "):].strip()
                try:
                    send_audio(sock, path)
                except Exception as e:
                    print(f"发送失败：{e}")
                continue

            if cmd == "playlocal":
                if not current_record_file:
                    print("当前还没有录音，请先执行 record")
                    continue
                try:
                    audio.play_wav(current_record_file)
                except Exception as e:
                    print(f"播放失败：{e}")
                continue

            if cmd.startswith("playlocal "):
                path = cmd[len("playlocal "):].strip()
                try:
                    audio.play_wav(path)
                except Exception as e:
                    print(f"播放失败：{e}")
                continue

            if cmd.startswith("rtstart"):
                parts = cmd.split(" ", 1)
                target_display_name = parts[1].strip() if len(parts) > 1 else ""
                start_rt_gui(target_display_name)
                continue

            if cmd == "rtstop":
                stop_rt_gui()
                continue

            if cmd == "quit":
                try:
                    send_json(sock, make_text_packet(username, "quit"))
                except Exception:
                    pass
                running = False
                break

            print("未知命令，输入 help 查看可用命令")

    except KeyboardInterrupt:
        running = False

    finally:
        stop_rt_gui()

        try:
            sock.close()
        except Exception:
            pass

        audio.terminate()
        print("客户端已关闭")


if __name__ == "__main__":
    main()