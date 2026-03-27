import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading, socket, time
from protocol import send_packet, recv_packet
from audio_manager import AudioManager
from config import HOST, PORT

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("IP电话终端")
        self.audio = AudioManager()
        self.name = f"User_{int(time.time())%1000}"
        self.target_user = None # 当前通话对象

        # --- UI 布局 ---
        # 左侧：电话本
        lb_frame = tk.Frame(root)
        lb_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        tk.Label(lb_frame, text="在线好友").pack()
        self.user_listbox = tk.Listbox(lb_frame, width=15)
        self.user_listbox.pack(fill=tk.Y, expand=True)
        self.user_listbox.bind('<Double-Button-1>', self.select_user)

        # 右侧：聊天
        main_frame = tk.Frame(root)
        main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat_area = scrolledtext.ScrolledText(main_frame, width=40, height=15)
        self.chat_area.pack(padx=5, pady=5)
        
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack()
        tk.Button(btn_frame, text="呼叫/锁定", command=self.select_user).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="录制语音", command=self.record_and_send).pack(side=tk.LEFT, padx=5)

        # 连接
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))
        send_packet(self.sock, "login", self.name)
        threading.Thread(target=self.receive_loop, daemon=True).start()

    def select_user(self, event=None):
        try:
            self.target_user = self.user_listbox.get(self.user_listbox.curselection())
            messagebox.showinfo("系统", f"已锁定目标: {self.target_user}")
        except:
            messagebox.showwarning("提醒", "请先在列表双击选择一个好友")

    def record_and_send(self):
        if not self.target_user:
            return messagebox.showwarning("错误", "请先选择呼叫对象")
        def task():
            data = self.audio.record_audio(3) # 录3秒
            send_packet(self.sock, "audio", self.name, {"target": self.target_user}, data)
            self.display(f"我 -> {self.target_user}: [语音已发送]")
        threading.Thread(target=task).start()

    def receive_loop(self):
        while True:
            packet = recv_packet(self.sock)
            if not packet: break
            header, payload = packet
            h_type = header.get('type')
            
            if h_type == "user_list":
                users = header.get('users', [])
                self.root.after(0, self.update_listbox, users)
            elif h_type == "audio":
                self.display(f"{header['sender']}: [语音来电]")
                threading.Thread(target=self.audio.play_audio, args=(payload,)).start()

    def update_listbox(self, users):
        self.user_listbox.delete(0, tk.END)
        for u in users:
            if u != self.name: self.user_listbox.insert(tk.END, u)

    def display(self, msg):
        self.chat_area.insert(tk.END, msg + "\n")
        self.chat_area.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk(); ChatClient(root); root.mainloop()