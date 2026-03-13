import socket
import threading
from config import HOST, PORT, BUFFER_SIZE, ENCODING

running = True


def receive_loop(sock: socket.socket):
    global running

    while running:
        try:
            data = sock.recv(BUFFER_SIZE)
            if not data:
                print("\n[!] 服务端已断开")
                running = False
                break

            msg = data.decode(ENCODING)
            print(f"\n收到：{msg}")

        except (ConnectionResetError, OSError):
            print("\n[!] 接收失败，连接已关闭")
            running = False
            break


def main():
    global running

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"已连接到 {HOST}:{PORT}")
    print("输入普通文本发送给 server，输入 quit 退出")

    recv_thread = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
    recv_thread.start()

    try:
        while running:
            msg = input("输入：").strip()
            if not msg:
                continue

            sock.sendall(msg.encode(ENCODING))

            if msg.lower() == "quit":
                running = False
                break

    except KeyboardInterrupt:
        print("\n客户端退出")
    finally:
        running = False
        try:
            sock.close()
        except:
            pass
        print("客户端已关闭")


if __name__ == "__main__":
    main()