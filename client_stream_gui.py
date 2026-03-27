# client_stream_gui.py
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import socket
import pyaudio
import collections
import time
from protocol import send_packet, recv_packet
from config import HOST, PORT, CHUNK, RATE, CHANNELS
from contact_manager import ContactManager
class RealTimeChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("VoIP 实时语音通信系统 (实验任务 6-8)")
        self.root.geometry("500x600")
        self.state = "IDLE"
        self.cm = ContactManager()
        # 核心参数：抖动缓冲区（Jitter Buffer）
        # 任务 8 优化：增加缓冲区可以减少卡顿，但会增加延迟
        self.buffer = collections.deque(maxlen=50) 
        self.is_recording = False
        self.my_name = f"User_{int(time.time())%1000}"

        # UI 建设
        self.chat_display = scrolledtext.ScrolledText(root, state='disabled', height=20)
        self.chat_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.btn_mic = tk.Button(root, text="🎤 开启实时对讲", font=("微软雅黑", 12), 
                                 command=self.toggle_mic, bg="#eeeeee")
        self.btn_mic.pack(pady=20)

        self.status_label = tk.Label(root, text="网络状态: 未连接", fg="red")
        self.status_label.pack()
        tk.Button(root, text="📞 呼叫", command=self.call_user).pack(pady=5)
        tk.Button(root, text="✅ 接听", command=self.accept_call).pack(pady=5)
        tk.Button(root, text="❌ 挂断", command=self.hangup).pack(pady=5)
        
        self.name_entry = tk.Entry(root)
        self.name_entry.pack(pady=5)

        self.addr_entry = tk.Entry(root)
        self.addr_entry.pack(pady=5)

        tk.Button(root, text="添加联系人", command=self.add_contact).pack(pady=5)
        # 初始化网络
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            self.status_label.config(text=f"网络状态: 已连接 (RTT 优化开启)", fg="green")
            
            # 开启接收线程和播放线程
            threading.Thread(target=self.receive_thread, daemon=True).start()
            threading.Thread(target=self.playback_thread, daemon=True).start()
        except Exception as e:
            messagebox.showerror("连接失败", f"无法连接到服务器: {e}")

    def log(self, msg):
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, msg + "\n")
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)

    def toggle_mic(self):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.btn_mic.config(text="🛑 停止对讲 (通话中...)", bg="#ff9999")
            threading.Thread(target=self.record_thread, daemon=True).start()
        else:
            self.btn_mic.config(text="🎤 开启实时对讲", bg="#eeeeee")

    def record_thread(self):
        """任务 6 & 8: 流式录音逻辑"""
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=CHANNELS, rate=RATE, 
                         input=True, frames_per_buffer=CHUNK)
        self.log("[系统] 麦克风已开启...")
        while self.is_recording:
            if self.state !="TALKING":
                time.sleep(0.1)
                continue
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                # 实时发送音频碎包
                send_packet(self.sock, "stream", self.my_name, binary_payload=data)
            except:
                break
        stream.stop_stream()
        stream.close()
        pa.terminate()
        self.log("[系统] 麦克风已关闭。")

    def receive_thread(self):
        """任务 7: 实时数据接收与解析"""
        while True:
            header, payload = recv_packet(self.sock)
            if not header:
                self.log("[错误] 与服务器断开连接")
                break
            
            if header['type'] == 'stream':
                if self.state == "TALKING":
                    self.buffer.append(payload)
                # 收到音频流，丢进 Jitter Buffer
                self.buffer.append(payload)
            elif header['type'] == 'text':
                self.log(f"{header['sender']}: {header.get('msg')}")
            elif header['type'] == 'call':
                 self.log(f"[系统] {header['sender']} 正在呼叫你")
                 self.state = "RINGING"

            elif header['type'] == 'accept':
                self.log("[系统] 对方已接听")
                self.state = "TALKING"

            elif header['type'] == 'hangup':
                self.log("[系统] 对方已挂断")
                self.state = "IDLE"

    def playback_thread(self):
        """任务 8 核心：带抖动缓冲的播放逻辑"""
        
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=CHANNELS, rate=RATE, 
                         output=True, frames_per_buffer=CHUNK)
        
        while True:
            # 只有当缓冲区积攒了足够的数据包（例如 5 个），才开始播放
            # 这样可以抵消网络传输不稳定的“抖动”
            if len(self.buffer) > 5:
                while len(self.buffer) > 0:
                    data = self.buffer.popleft()
                    stream.write(data)
            else:
                time.sleep(0.01) # 缓冲不足时稍作等待
    
    def call_user(self):
     if self.state != "IDLE":
         self.log("[系统] 当前状态无法呼叫")
         return

     send_packet(self.sock, "call", self.my_name)
     self.state = "CALLING"
     self.log("[系统] 正在呼叫...")

    def accept_call(self):
     if self.state != "RINGING":
         return

     send_packet(self.sock, "accept", self.my_name)
     self.state = "TALKING"
     self.log("[系统] 已接听")

    def hangup(self):
     send_packet(self.sock, "hangup", self.my_name)
     self.state = "IDLE"
     self.log("[系统] 已挂断")


    def add_contact(self):
        name = self.name_entry.get()
        addr = self.addr_entry.get()
        self.cm.add(name, addr)
        self.log(f"[电话本] 已添加 {name}")
if __name__ == "__main__":
    root = tk.Tk()
    client = RealTimeChatClient(root)
    root.mainloop()