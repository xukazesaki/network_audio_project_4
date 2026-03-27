import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import threading
import socket
import pyaudio
import collections
import time
import os
import json
# 导入咱们自己的模块
from protocol import send_packet, recv_packet
from audio_manager import AudioManager
from config import HOST, PORT, CHUNK, RATE, CHANNELS

class MultiFunctionClient:
    def __init__(self, root):
        self.root = root
        self.root.title("东南大学计网实践 - 综合音频终端 (微信版)")
        self.root.geometry("600x700")

        # --- 核心参数初始化 ---
        self.audio_manager = AudioManager()
        self.buffer = collections.deque(maxlen=50) 
        self.is_recording = False # 修复报错：在这里初始化
        self.my_name = f"User_{int(time.time())%1000}"
        self.target_user = None 

        # --- UI 布局 ---
        
        # 顶部：QoS 状态
        self.qos_label = tk.Label(root, text="缓冲区: 0 | 目标: 未选择", fg="blue", font=('Arial', 10, 'bold'))
        self.qos_label.pack(pady=5)

        # 中间：左边电话本，右边聊天
        middle_frame = tk.Frame(root)
        middle_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # 电话本 (任务 4)
        list_frame = tk.Frame(middle_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        tk.Label(list_frame, text="在线好友").pack()
        self.user_listbox = tk.Listbox(list_frame, width=15, bg="#f8f8f8")
        self.user_listbox.pack(fill=tk.Y, expand=True)
        self.user_listbox.bind('<<ListboxSelect>>', self.on_user_select)
        self.contacts_file = "contacts.json"
        self.contacts = self.load_contacts()  # 启动时自动加载
        self.refresh_user_listbox()
        # 任务 8 扩展：保存按钮
        tk.Button(list_frame, text="⭐ 存为常用", command=self.save_contact).pack(fill=tk.X)
        btn_fm = tk.Frame(list_frame)
        btn_fm.pack(fill=tk.X)
        
        tk.Button(btn_fm, text="添加/改备注", command=self.ui_add_contact, font=('Arial', 8)).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_fm, text="删除好友", command=self.ui_del_contact, font=('Arial', 8)).pack(side=tk.LEFT, expand=True, fill=tk.X)
        # 聊天显示 (微信样式)
        self.chat_display = scrolledtext.ScrolledText(middle_frame, state='disabled', bg="white")
        self.chat_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 配置对齐标签
        self.chat_display.tag_configure("self_msg", justify='right', foreground="#07C160", spacing1=5) 
        self.chat_display.tag_configure("other_msg", justify='left', foreground="black", spacing1=5)
        self.chat_display.tag_configure("system", justify='center', foreground="gray", font=('Arial', 9))

        # 底部：输入和控制
        controls = tk.Frame(root)
        controls.pack(fill=tk.X, padx=10, pady=10)

        self.input_entry = tk.Entry(controls)
        self.input_entry.pack(side=tk.TOP, fill=tk.X, pady=5)
        self.input_entry.bind("<Return>", lambda e: self.send_text())
        
        btn_grid = tk.Frame(controls)
        btn_grid.pack(side=tk.TOP, fill=tk.X)

        tk.Button(btn_grid, text="发送文字", command=self.send_text, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid, text="📁 发送文件", command=self.send_file, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_grid, text="🎤 录音5秒发送", command=self.send_offline_voice, width=15, bg="#e1f5fe").pack(side=tk.LEFT, padx=2)
        
        self.btn_mic = tk.Button(controls, text="🔊 开启实时通话", command=self.toggle_realtime_mic, 
                                 bg="#eeeeee", font=('Arial', 10, 'bold'))
        self.btn_mic.pack(fill=tk.X, pady=5)

        self.connect_server()

    # --- 逻辑功能 ---

    def log(self, msg, align="left"):
        """微信对齐逻辑"""
        self.chat_display.config(state='normal')
        tag = "self_msg" if align == "right" else ("system" if align == "center" else "other_msg")
        self.chat_display.insert(tk.END, msg + "\n", tag)
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)

    def save_contact(self):
        """保存固定账户到本地文本"""
        if not self.target_user: return
        with open("saved_contacts.txt", "a", encoding="utf-8") as f:
            f.write(self.target_user + "\n")
        self.log(f"[系统] 已记录联系人: {self.target_user}", align="center")

    def on_user_select(self, event):
        selection = self.user_listbox.curselection()
        if selection:
            self.target_user = self.user_listbox.get(selection[0])
            self.qos_label.config(text=f"当前目标: {self.target_user}")
            self.log(f"--- 正在与 {self.target_user} 对话 ---", align="center")

    def send_text(self):
        msg = self.input_entry.get()
        if msg and self.target_user:
            send_packet(self.sock, "text", self.my_name, {"target": self.target_user, "msg": msg})
            self.log(f"我: {msg}", align="right") # 自己发的靠右
            self.input_entry.delete(0, tk.END)
        else:
            messagebox.showwarning("提醒", "请先选择好友")

    def send_offline_voice(self):
        if not self.target_user: return messagebox.showwarning("错误", "请选择好友")
        def task():
            self.log("...正在录制5秒语音...", align="center")
            data = self.audio_manager.record_audio(5)
            send_packet(self.sock, "audio", self.my_name, {"target": self.target_user}, data)
            self.log("我: [语音消息]", align="right")
        threading.Thread(target=task, daemon=True).start()
    

    def ui_add_contact(self):
        """弹出窗口添加好友"""
        if not self.target_user:
            return messagebox.showwarning("提醒", "请先在列表中选中一个在线用户")
        
        # 简单的输入框获取备注
        import tkinter.simpledialog as sd
        remark = sd.askstring("添加好友", f"为 {self.target_user} 输入备注:", initialvalue="常用联系人")
        if remark:
            self.add_contact(self.target_user, remark)

    def ui_del_contact(self):
        """删除选中的好友"""
        if not self.target_user: return
        if messagebox.askyesno("确认", f"确定要从电话本删除 {self.target_user} 吗？"):
            self.delete_contact(self.target_user)

    def refresh_user_listbox(self, online_users=None):
        """整合在线状态和持久化数据的显示"""
        self.user_listbox.delete(0, tk.END)
        
        # 获取所有已保存的联系人
        saved_names = self.contacts.keys()
        
        # 如果当前有在线列表，就显示在线的；否则显示保存的
        display_list = online_users if online_users is not None else list(saved_names)
        
        for u in display_list:
            if u == self.my_name: continue
            
            # 如果是已保存的好友，显示备注
            prefix = "⭐ " if u in self.contacts else "👤 "
            remark = f" ({self.contacts[u]})" if u in self.contacts else ""
            self.user_listbox.insert(tk.END, f"{prefix}{u}{remark}")
    # 3. 发送文件 (任务 4)
    def send_file(self):
        if not self.target_user: 
            return messagebox.showwarning("错误", "请先在左侧选择好友再发送文件")
        
        # 弹出文件选择对话框
        fpath = filedialog.askopenfilename(
            title="选择要发送的文件",
            filetypes=[("WAV音频", "*.wav"), ("所有文件", "*.*")]
        )
        
        if fpath:
            try:
                fname = os.path.basename(fpath)
                with open(fpath, "rb") as f:
                    file_data = f.read()
                
                # 发送文件包：包含文件名
                send_packet(self.sock, "file", self.my_name, 
                            {"target": self.target_user, "filename": fname}, 
                            file_data)
                
                self.log(f"我: [发送文件] {fname}", align="right")
            except Exception as e:
                messagebox.showerror("错误", f"文件发送失败: {e}")
    def toggle_realtime_mic(self):
        if not self.target_user: return messagebox.showwarning("错误", "通话前请选择好友")
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.btn_mic.config(text="🛑 停止通话", bg="#ff9999")
            threading.Thread(target=self.record_stream_thread, daemon=True).start()
        else:
            self.btn_mic.config(text="🔊 开启实时通话", bg="#eeeeee")

    def record_stream_thread(self):
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        while self.is_recording:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                send_packet(self.sock, "stream", self.my_name, {"target": self.target_user}, data)
            except: break
        stream.stop_stream(); stream.close(); pa.terminate()

    # --- 电话本持久化逻辑 ---
    
    def load_contacts(self):
        """读取本地 JSON 文件"""
        if os.path.exists(self.contacts_file):
            with open(self.contacts_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except:
                    return {} # 如果文件损坏则返回空字典
        return {} # 格式: {"用户名": "备注/描述", ...}

    def save_contacts_to_disk(self):
        """保存到本地文件"""
        with open(self.contacts_file, "w", encoding="utf-8") as f:
            json.dump(self.contacts, f, ensure_ascii=False, indent=4)

    def add_contact(self, name, remark="好友"):
        """【增/改】添加或更新联系人"""
        self.contacts[name] = remark
        self.save_contacts_to_disk()
        self.log(f"[系统] 已保存联系人: {name} ({remark})", align="center")
        self.refresh_user_listbox()

    def delete_contact(self, name):
        """【删】删除联系人"""
        if name in self.contacts:
            del self.contacts[name]
            self.save_contacts_to_disk()
            self.log(f"[系统] 已删除联系人: {name}", align="center")
            self.refresh_user_listbox()

    def refresh_user_listbox(self):
        """【查】刷新列表框显示"""
        # 这里的逻辑需要兼容“在线用户”和“保存的联系人”
        # 我们可以在名字前面加个星号标识已保存的好友
        pass # 见下文完整 UI 逻辑
    def receive_thread(self):
        while True:
            header, payload = recv_packet(self.sock)
            if not header: break
            h_type, sender = header.get('type'), header.get('sender')

            if h_type == 'user_list':
                users = header.get('users', [])
                self.user_listbox.delete(0, tk.END)
                for u in users:
                    if u != self.my_name: self.user_listbox.insert(tk.END, u)
            elif h_type == 'text':
                self.log(f"{sender}: {header.get('msg')}", align="left") # 别人发的靠左
            elif h_type == 'audio':
                self.log(f"{sender}: [语音消息]", align="left")
                threading.Thread(target=self.audio_manager.play_audio, args=(payload,), daemon=True).start()
            elif h_type == 'stream':
                self.buffer.append(payload)
            elif h_type == 'file':
                fname = header.get('filename', 'new_file.wav')
                self.log(f"[文件] 来自 {sender}: {fname}", align="left")
                if not os.path.exists("received"): os.makedirs("received")
                with open(f"received/{fname}", "wb") as f: f.write(payload)

    # ... 其余 connect_server, playback_thread, qos_monitor 保持不变 ...
    def connect_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            send_packet(self.sock, "login", self.my_name)
            self.log(f"欢迎登录！你的 ID 是: {self.my_name}", align="center")
            threading.Thread(target=self.receive_thread, daemon=True).start()
            threading.Thread(target=self.playback_thread, daemon=True).start()
            threading.Thread(target=self.qos_monitor, daemon=True).start()
        except Exception as e:
            messagebox.showerror("错误", f"连接失败: {e}")

    def playback_thread(self):
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
        while True:
            if len(self.buffer) > 5:
                while len(self.buffer) > 0: stream.write(self.buffer.popleft())
            else: time.sleep(0.01)

    def qos_monitor(self):
        while True:
            self.qos_label.config(text=f"缓冲区深度: {len(self.buffer)} | 目标: {self.target_user}")
            time.sleep(0.5)

if __name__ == "__main__":
    root = tk.Tk(); client = MultiFunctionClient(root); root.mainloop()