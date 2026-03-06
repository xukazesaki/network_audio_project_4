import socket
from config import HOST, PORT, BUFFER_SIZE, ENCODING

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"已连接到 {HOST}:{PORT}")

    try:
        while True:
            msg = input("输入：").strip()
            if not msg:
                continue
            sock.sendall(msg.encode(ENCODING))

            if msg.lower() == "quit":
                break

            data = sock.recv(BUFFER_SIZE)
            if not data:
                print("服务端断开")
                break
            print("收到：", data.decode(ENCODING))
    finally:
        sock.close()

if __name__ == "__main__":
    main()