import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import socket
import time
from protocol import Protocol
from audio_manager import AudioManager
from config import HOST, PORT

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Python 网络音频聊天室")
        self.audio = AudioManager()
        self.name = f"User_{int(time.time()) % 1000}"
        
        # UI 布局
        self.chat_area = scrolledtext.ScrolledText(root, width=50, height=20)
        self.chat_area.pack(padx=10, pady=10)
        
        self.msg_entry = tk.Entry(root, width=40)
        self.msg_entry.pack(side=tk.LEFT, padx=10)
        
        tk.Button(root, text="发送", command=self.send_text).pack(side=tk.LEFT)
        tk.Button(root, text="按住说话", command=self.record_and_send).pack(side=tk.LEFT, padx=5)

        # 网络连接
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((HOST, PORT))
            threading.Thread(target=self.receive_loop, daemon=True).start()
        except:
            messagebox.showerror("错误", "无法连接服务器")

    def send_text(self):
        txt = self.msg_entry.get()
        if txt:
            Protocol.send_packet(self.sock, "text", self.name, {"content": txt})
            self.display(f"我: {txt}")
            self.msg_entry.delete(0, tk.END)

    def record_and_send(self):
        def task():
            self.display("系统: 正在录音5秒...")
            data = self.audio.record_audio(5)
            Protocol.send_packet(self.sock, "audio", self.name, extra_bytes=data)
            self.display("系统: 语音已发送")
        threading.Thread(target=task).start()

    def receive_loop(self):
        while True:
            packet = Protocol.recv_packet(self.sock)
            if not packet: break
            header, extra = packet
            
            if header['type'] == "text":
                self.display(f"{header['sender']}: {header.get('content')}")
            elif header['type'] == "audio":
                self.display(f"{header['sender']}: [语音消息]")
                threading.Thread(target=self.audio.play_audio, args=(extra,)).start()

    def display(self, msg):
        self.chat_area.insert(tk.END, msg + "\n")
        self.chat_area.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    client = ChatClient(root)
    root.mainloop()