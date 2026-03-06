import socket
import threading
from config import HOST, PORT, BUFFER_SIZE, ENCODING

def handle_client(conn: socket.socket, addr):
    print(f"[+] 客户端接入：{addr}")
    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                print(f"[-] 客户端断开：{addr}")
                break

            msg = data.decode(ENCODING).strip()
            print(f"[{addr}] {msg}")

            if msg.lower() == "quit":
                # 客户端主动结束
                break

            # 回显：原样发回客户端（也可以加前缀）
            reply = f"server echo: {msg}"
            conn.sendall(reply.encode(ENCODING))

    except (ConnectionResetError, OSError) as e:
        print(f"[!] 连接异常 {addr}: {e}")
    finally:
        try:
            conn.close()
        except:
            pass

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(20)
    print(f"服务端监听中：{HOST}:{PORT}")

    try:
        while True:
            conn, addr = server_socket.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[!] 服务端收到 Ctrl+C，准备退出")
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()