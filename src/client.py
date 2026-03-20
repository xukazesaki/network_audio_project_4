import os
import socket
import threading

from audio_utils import play_wav, record_until_enter
from config import (
    CLIENT_RECEIVE_DIR,
    RECORDED_DIR,
    HOST,
    PORT,
)
from protocol import (
    make_audio_packet,
    make_text_packet,
    make_register_packet,
    make_private_packet,
    make_list_packet,
    recv_file_bytes,
    recv_json,
    send_file_bytes,
    send_json,
)

running = True
current_record_file = None
username = None


def ensure_client_dir():
    """
    确保客户端接收音频的目录存在。
    """
    os.makedirs(CLIENT_RECEIVE_DIR, exist_ok=True)


def ensure_recorded_dir():
    """
    确保本地录音目录存在。
    """
    os.makedirs(RECORDED_DIR, exist_ok=True)


def get_next_record_file():
    """
    在 recorded 目录中自动生成下一个录音文件名：
    record1.wav, record2.wav, record3.wav ...
    """
    ensure_recorded_dir()

    max_index = 0
    for name in os.listdir(RECORDED_DIR):
        if not name.lower().endswith(".wav"):
            continue

        base = os.path.splitext(name)[0]
        if not base.startswith("record"):
            continue

        num_part = base[6:]  # 取出 "record" 后面的数字
        if num_part.isdigit():
            max_index = max(max_index, int(num_part))

    next_index = max_index + 1
    return os.path.join(RECORDED_DIR, f"record{next_index}.wav")


def receive_loop(sock: socket.socket):
    """
    客户端接收线程：
    持续接收服务端消息，不阻塞主线程输入。
    """
    global running

    ensure_client_dir()

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

            elif msg_type == "audio_file":
                sender = meta.get("sender", "UNKNOWN")
                filename = meta["filename"]
                file_size = meta["file_size"]

                save_name = f"from_{sender}_{filename}"
                save_path = os.path.join(CLIENT_RECEIVE_DIR, save_name)

                print(f"\n收到来自 {sender} 的音频文件：{filename} ({file_size} bytes)")
                recv_file_bytes(sock, save_path, file_size)
                print(f"已保存到：{save_path}")

                # 如不想自动播放，可删掉下面这段
                try:
                    play_wav(save_path)
                except Exception as e:
                    print(f"播放失败：{e}")

            else:
                print(f"\n收到未知类型消息：{meta}")

        except (ConnectionError, OSError):
            print("\n[!] 与服务端连接已断开")
            running = False
            break


def print_help():
    """
    打印客户端支持的命令。
    """
    print("\n可用命令：")
    print("  msg <消息>             发送文本到服务端")
    print("  pm <用户名> <消息>     私发给指定用户")
    print("  list                   查看在线用户")
    print("  record                 按 Enter 开始录音，再按 Enter 结束")
    print("  sendaudio              发送最近一次录音给服务端")
    print("  pmaudio <用户名>       把最近一次录音私发给指定用户")
    print("  pmaudio <用户名> <路径> 私发指定音频文件给指定用户")
    print("  playlocal              播放最近一次录音")
    print("  playlocal <路径>       播放指定本地音频文件")
    print("  help                   查看命令")
    print("  quit                   退出客户端")


def send_audio(sock: socket.socket, file_path: str,target=None):
    """
    发送音频文件给服务端。
    先发元信息，再发文件内容。
    """
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        return

    send_json(sock, make_audio_packet(username, file_path, target))
    send_file_bytes(sock, file_path)

    if target:
        print(f"音频已私发给 {target}：{file_path}")
    else:
        print(f"音频发送完成：{file_path}")

def register_username(sock: socket.socket):
    """
    连接成功后，循环要求用户输入用户名，直到注册成功。
    """
    global username

    while True:
        username = input("请输入用户名：").strip()
        if not username:
            print("用户名不能为空")
            continue

        send_json(sock, make_register_packet(username))
        meta = recv_json(sock)

        if meta.get("type") == "system":
            text = meta.get("text", "")
            print(text)
            if "注册成功" in text:
                break
        else:
            print("注册响应异常，请重试")


def main():
    """
    客户端主程序入口。
    """
    global running
    global current_record_file

    ensure_client_dir()
    ensure_recorded_dir()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    # 先注册用户名
    register_username(sock)

    print(f"已连接到服务端 {HOST}:{PORT}")
    print(f"当前用户名：{username}")
    print(f"录音目录：{RECORDED_DIR}")
    print_help()

    # 启动接收线程
    recv_thread = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
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
                try:
                    send_json(sock, make_list_packet())
                except Exception as e:
                    print(f"发送失败：{e}")
                    running = False
                    break
                continue

            if cmd.startswith("pm "):
                parts = cmd.split(" ", 2)
                if len(parts) < 3:
                    print("格式错误，应为：pm <用户名> <消息>")
                    continue

                target = parts[1].strip()
                text = parts[2].strip()

                if not target or not text:
                    print("目标用户名和消息不能为空")
                    continue

                try:
                    send_json(sock, make_private_packet(username, target, text))
                except Exception as e:
                    print(f"发送失败：{e}")
                    running = False
                    break
                continue

            if cmd == "record":
                try:
                    current_record_file = get_next_record_file()
                    record_until_enter(current_record_file)
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
                    play_wav(current_record_file)
                except Exception as e:
                    print(f"播放失败：{e}")
                continue

            if cmd.startswith("playlocal "):
                path = cmd[len("playlocal "):].strip()
                try:
                    play_wav(path)
                except Exception as e:
                    print(f"播放失败：{e}")
                continue

            if cmd == "quit":
                try:
                    send_json(sock, make_text_packet(username, "quit"))
                except:
                    pass
                running = False
                break

            if cmd.startswith("msg "):
                text = cmd[4:].strip()
                if not text:
                    print("消息不能为空")
                    continue

                try:
                    send_json(sock, make_text_packet(username, text))
                except Exception as e:
                    print(f"发送失败：{e}")
                    running = False
                    break
                continue

            print("未知命令，输入 help 查看可用命令")

    except KeyboardInterrupt:
        running = False

    finally:
        try:
            sock.close()
        except:
            pass
        print("客户端已关闭")


if __name__ == "__main__":
    main()