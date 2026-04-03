import collections
import os
import socket
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog

import pyaudio


from src.core.audio_manager import AudioManager
from src.core.config import (
    CHANNELS,
    CHUNK,
    FORMAT,
    HOST,
    JITTER_BUFFER_MAXLEN,
    JITTER_START_THRESHOLD,
    PORT,
    RATE,
    RECEIVE_DIR,
)
from src.core.contact_manager import ContactManager
from src.core.protocol import recv_packet, send_packet


class MultiFunctionClient:
    # 初始化主客户端窗口、通话状态以及网络和音频组件。
    def __init__(self, root):
        self.root = root
        self.root.title("综合音频终端")
        self.root.geometry("780x760")

        self.sock = None
        self.running = True
        self.is_recording = False
        self.buffer = collections.deque(maxlen=JITTER_BUFFER_MAXLEN)
        self.audio_manager = AudioManager()
        self.contact_manager = ContactManager()

        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        threading.Thread(target=self.udp_receive_thread, daemon=True).start()
        
        default_name = f"User_{int(time.time()) % 1000}"
        entered_name = simpledialog.askstring(
            "用户名",
            "请输入用户名：",
            initialvalue=default_name,
            parent=root,
        )
        self.my_name = (entered_name or default_name).strip() or default_name

        self.target_user = None
        self.online_users = []
        self.contacts = self.contact_manager.get_all()
        self.user_index_map = {}
        self.play_stream = None
        self.stream_pa = None

        self.call_state = "IDLE"
        self.call_peer = None
        self.ringing_from = None

        self._build_ui()
        self.refresh_user_listbox()
        self.connect_server()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(400, self.update_status)

    # 创建联系人、聊天区、通话控制和媒体控制的完整界面布局。
    def _build_ui(self):
        self.status_label = tk.Label(
            self.root,
            text="状态: 空闲 | 缓冲区: 0 | 目标: 未选择 | 在线: 0",
            fg="blue",
            font=("Arial", 10, "bold"),
        )
        self.status_label.pack(pady=6)

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        sidebar = tk.Frame(body)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(sidebar, text="在线用户 / 联系人").pack(anchor="w")
        self.user_listbox = tk.Listbox(sidebar, width=28, height=24, bg="#f8f8f8")
        self.user_listbox.pack(fill=tk.Y, expand=True)
        self.user_listbox.bind("<<ListboxSelect>>", self.on_user_select)
        self.user_listbox.bind("<Double-Button-1>", self.on_user_select)

        tk.Button(sidebar, text="设为当前目标", command=self.on_user_select).pack(fill=tk.X, pady=(8, 4))
        tk.Button(sidebar, text="保存联系人", command=self.save_contact).pack(fill=tk.X, pady=4)
        tk.Button(sidebar, text="添加/改备注", command=self.ui_add_contact).pack(fill=tk.X, pady=4)
        tk.Button(sidebar, text="删除联系人", command=self.ui_del_contact).pack(fill=tk.X, pady=4)

        main = tk.Frame(body)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_display = scrolledtext.ScrolledText(main, state="disabled", bg="white")
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        self.chat_display.tag_configure("self_msg", justify="right", foreground="#0b7f3f", spacing1=4)
        self.chat_display.tag_configure("other_msg", justify="left", foreground="black", spacing1=4)
        self.chat_display.tag_configure("system", justify="center", foreground="gray", spacing1=4)

        controls = tk.Frame(self.root)
        controls.pack(fill=tk.X, padx=10, pady=10)

        self.input_entry = tk.Entry(controls)
        self.input_entry.pack(fill=tk.X, pady=(0, 8))
        self.input_entry.bind("<Return>", lambda _: self.send_text())

        button_row = tk.Frame(controls)
        button_row.pack(fill=tk.X)

        tk.Button(button_row, text="发送文字", command=self.send_text, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(button_row, text="发送文件", command=self.send_file, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(button_row, text="录音 5 秒发送", command=self.send_offline_voice, width=14).pack(side=tk.LEFT, padx=2)

        call_row = tk.Frame(controls)
        call_row.pack(fill=tk.X, pady=(8, 0))
        tk.Button(call_row, text="呼叫", command=self.call_user, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(call_row, text="接听", command=self.accept_call, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(call_row, text="挂断", command=self.hangup, width=10).pack(side=tk.LEFT, padx=2)

        self.btn_mic = tk.Button(
            controls,
            text="开启实时通话",
            command=self.toggle_realtime_mic,
            bg="#eeeeee",
            font=("Arial", 10, "bold"),
        )
        self.btn_mic.pack(fill=tk.X, pady=8)

    # 向主消息区追加一条带样式的文本。
    def log(self, msg, align="left"):
        self.chat_display.config(state="normal")
        tag = "self_msg" if align == "right" else ("system" if align == "center" else "other_msg")
        self.chat_display.insert(tk.END, msg + "\n", tag)
        self.chat_display.config(state="disabled")
        self.chat_display.see(tk.END)

    # 让后台线程安全地向界面追加日志。
    def safe_log(self, msg, align="left"):
        self.root.after(0, lambda: self.log(msg, align))

    # 从联系人管理器刷新内存中的联系人缓存。
    def refresh_contacts(self):
        self.contacts = self.contact_manager.get_all()

    # 将当前目标保存为联系人，备注使用已有值或默认值。
    def save_contact(self):
        if not self.target_user:
            return messagebox.showwarning("提示", "请先选择一个目标用户")
        remark = self.contact_manager.get(self.target_user, "常用联系人")
        self.contact_manager.add(self.target_user, remark)
        self.refresh_contacts()
        self.refresh_user_listbox()
        self.log(f"[系统] 已保存联系人: {self.target_user} ({remark})", align="center")

    # 弹出输入框，为当前选中用户保存自定义备注。
    def ui_add_contact(self):
        if not self.target_user:
            return messagebox.showwarning("提示", "请先在左侧选择一个在线用户")
        remark = simpledialog.askstring(
            "添加好友",
            f"为 {self.target_user} 输入备注：",
            initialvalue=self.contact_manager.get(self.target_user, "常用联系人"),
            parent=self.root,
        )
        if remark:
            self.contact_manager.add(self.target_user, remark.strip())
            self.refresh_contacts()
            self.refresh_user_listbox()
            self.log(f"[系统] 已保存联系人: {self.target_user} ({remark.strip()})", align="center")

    # 在用户确认后删除当前选中的联系人。
    def ui_del_contact(self):
        if not self.target_user:
            return messagebox.showwarning("提示", "请先选择一个联系人")
        if messagebox.askyesno("确认", f"确定要删除联系人 {self.target_user} 吗？"):
            self.contact_manager.delete(self.target_user)
            self.refresh_contacts()
            self.refresh_user_listbox()
            self.log(f"[系统] 已删除联系人: {self.target_user}", align="center")

    # 根据在线用户和已保存联系人重建侧边栏列表。
    def refresh_user_listbox(self):
        self.refresh_contacts()
        self.user_listbox.delete(0, tk.END)
        self.user_index_map.clear()

        names = sorted(set(self.online_users) | set(self.contacts.keys()))
        insert_index = 0
        for username in names:
            if username == self.my_name:
                continue

            online = username in self.online_users
            prefix = "在线" if online else "离线"
            remark = self.contacts.get(username)
            label = f"[{prefix}] {username}"
            if remark:
                label += f" ({remark})"

            self.user_listbox.insert(tk.END, label)
            self.user_index_map[insert_index] = username
            insert_index += 1

    # 根据列表选中项更新当前聊天或通话目标。
    def on_user_select(self, event=None):
        selection = self.user_listbox.curselection()
        if not selection:
            return
        username = self.user_index_map.get(selection[0])
        if not username:
            return
        self.target_user = username
        self.log(f"[系统] 当前目标已切换为: {self.target_user}", align="center")

    # 建立 socket 连接，并启动接收线程和播放线程。
    def connect_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            send_packet(self.sock, "login", self.my_name)

            self.stream_pa = pyaudio.PyAudio()
            self.play_stream = self.stream_pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                frames_per_buffer=CHUNK,
            )

            self.log(f"[系统] 欢迎登录，当前用户: {self.my_name}", align="center")
            threading.Thread(target=self.receive_thread, daemon=True).start()
            threading.Thread(target=self.playback_thread, daemon=True).start()
        except Exception as e:
            self.running = False
            messagebox.showerror("错误", f"连接失败: {e}")

    # 为必须先选择目标用户的操作做前置检查。
    def require_target(self):
        if not self.target_user:
            messagebox.showwarning("提示", "请先选择目标用户")
            return False
        return True

    # 向当前目标用户发送文本消息。
    def send_text(self):
        if not self.require_target():
            return

        msg = self.input_entry.get().strip()
        if not msg:
            return

        send_packet(self.sock, "text", self.my_name, {"target": self.target_user, "msg": msg})
        self.log(f"我 -> {self.target_user}: {msg}", align="right")
        self.input_entry.delete(0, tk.END)

    # 选择本地文件并发送给当前目标用户。
    def send_file(self):
        if not self.require_target():
            return

        fpath = filedialog.askopenfilename(
            title="选择要发送的文件",
            filetypes=[("所有文件", "*.*")],
        )
        if not fpath:
            return

        try:
            with open(fpath, "rb") as f:
                file_data = f.read()
            filename = os.path.basename(fpath)
            send_packet(
                self.sock,
                "file",
                self.my_name,
                {"target": self.target_user, "filename": filename},
                file_data,
            )
            self.log(f"我 -> {self.target_user}: [文件] {filename}", align="right")
        except Exception as e:
            messagebox.showerror("错误", f"文件发送失败: {e}")

    # 录制一段短语音，并作为离线语音消息发送。
    def send_offline_voice(self):
        if not self.require_target():
            return

        def task():
            try:
                self.safe_log("[系统] 正在录制 5 秒语音...", align="center")
                data = self.audio_manager.record_audio(5)
                send_packet(self.sock, "audio", self.my_name, {"target": self.target_user}, data)
                self.safe_log(f"我 -> {self.target_user}: [语音消息]", align="right")
            except Exception as e:
                self.safe_log(f"[系统] 录音发送失败: {e}", align="center")

        threading.Thread(target=task, daemon=True).start()

    # 向当前选中的目标用户发起呼叫请求。
    def call_user(self):
        if not self.require_target():
            return
        if self.call_state != "IDLE":
            messagebox.showwarning("提示", "当前已有通话流程，请先挂断")
            return

        self.call_state = "CALLING"
        self.call_peer = self.target_user
        send_packet(self.sock, "call", self.my_name, {"target": self.target_user})
        self.log(f"[系统] 正在呼叫 {self.target_user}...", align="center")

    # 接听当前正在响铃的来电。
    def accept_call(self):
        if self.call_state != "RINGING" or not self.ringing_from:
            messagebox.showwarning("提示", "当前没有待接听来电")
            return

        self.call_peer = self.ringing_from
        self.target_user = self.ringing_from
        self.call_state = "TALKING"
        send_packet(self.sock, "accept", self.my_name, {"target": self.ringing_from})
        self.log(f"[系统] 已接听 {self.ringing_from}", align="center")
        self.ringing_from = None

    # 挂断当前正在进行或等待中的通话。
    def hangup(self):
        peer = self.call_peer or self.ringing_from or self.target_user
        if not peer:
            messagebox.showwarning("提示", "当前没有可挂断的通话")
            return

        send_packet(self.sock, "hangup", self.my_name, {"target": peer})
        self._reset_call_state()
        self.log("[系统] 已挂断", align="center")

    # 将所有通话相关状态重置为空闲状态。
    def _reset_call_state(self):
        self.call_state = "IDLE"
        self.call_peer = None
        self.ringing_from = None
        self.is_recording = False
        self.root.after(0, lambda: self.btn_mic.config(text="开启实时通话", bg="#eeeeee"))

    # 在通话进行中开启或停止实时麦克风流发送。
    def toggle_realtime_mic(self):
        if self.call_state != "TALKING":
            messagebox.showwarning("提示", "请先建立通话，再开启实时语音")
            return

        self.is_recording = not self.is_recording
        if self.is_recording:
            self.btn_mic.config(text="停止实时通话", bg="#ff9999")
            threading.Thread(target=self.record_stream_thread, daemon=True).start()
            self.log(f"[系统] 已开始与 {self.call_peer} 实时通话", align="center")
        else:
            self.btn_mic.config(text="开启实时通话", bg="#eeeeee")
            self.log("[系统] 已停止实时语音", align="center")

    # 持续采集麦克风数据块，并实时发送给通话对端。
    def record_stream_thread(self):
        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            from src.core.config import HOST, UDP_PORT 
            server_address = (HOST, UDP_PORT) # 10.192.42.148, 5007
            
            while self.running and self.is_recording and self.call_state == "TALKING" and self.call_peer:
                data = stream.read(CHUNK, exception_on_overflow=False)
                #send_packet(self.sock, "stream", self.my_name, {"target": self.call_peer}, data)
                self.udp_sock.sendto(data, server_address)
        except Exception as e:
            if self.running:
                self.safe_log(f"[系统] 实时语音发送失败: {e}", align="center")
        finally:
            self.is_recording = False
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            pa.terminate()
            self.root.after(0, lambda: self.btn_mic.config(text="开启实时通话", bg="#eeeeee"))

    # 持续接收服务端数据包，并按消息类型分发处理。
    def receive_thread(self):
        while self.running:
            header, payload = recv_packet(self.sock)
            if not header:
                if self.running:
                    self.safe_log("[系统] 与服务器连接已断开", align="center")
                self.running = False
                break

            msg_type = header.get("type")
            sender = header.get("sender", "未知用户")

            if msg_type == "user_list":
                self.online_users = header.get("users", [])
                self.root.after(0, self.refresh_user_listbox)
            elif msg_type == "text":
                self.safe_log(f"{sender}: {header.get('msg', '')}", align="left")
            elif msg_type == "audio":
                self.safe_log(f"{sender}: [语音消息]", align="left")
                threading.Thread(target=self.audio_manager.play_audio, args=(payload,), daemon=True).start()
            elif msg_type == "stream":
                if payload and self.call_state == "TALKING":
                    self.buffer.append(payload)
            elif msg_type == "file":
                filename = header.get("filename", "new_file.bin")
                os.makedirs(RECEIVE_DIR, exist_ok=True)
                save_path = os.path.join(RECEIVE_DIR, f"from_{sender}_{filename}")
                with open(save_path, "wb") as f:
                    f.write(payload)
                self.safe_log(f"{sender}: [文件] {filename} 已保存到 {save_path}", align="left")
            elif msg_type == "call":
                self.ringing_from = sender
                self.call_state = "RINGING"
                self.safe_log(f"[系统] {sender} 正在呼叫你", align="center")
                self.root.after(0, lambda: messagebox.showinfo("来电", f"{sender} 正在呼叫你"))
            elif msg_type == "accept":
                self.call_peer = sender
                self.target_user = sender
                self.call_state = "TALKING"
                self.safe_log(f"[系统] {sender} 已接听，通话建立", align="center")
            elif msg_type == "hangup":
                self.safe_log(f"[系统] {sender} 已挂断", align="center")
                self._reset_call_state()
            else:
                self.safe_log(f"[系统] 收到未知消息类型: {msg_type}", align="center")

    # 当缓冲区积累到足够数据后，播放实时语音。
    def playback_thread(self):
        while self.running:
            try:
                if (
                    self.call_state == "TALKING"
                    and len(self.buffer) >= JITTER_START_THRESHOLD
                    and self.play_stream is not None
                ):
                    self.play_stream.write(self.buffer.popleft())
                else:
                    time.sleep(0.01)
            except Exception as e:
                if self.running:
                    self.safe_log(f"[系统] 播放失败: {e}", align="center")
                time.sleep(0.05)

    # 刷新窗口顶部显示的简要状态栏。
    def update_status(self):
        state_map = {
            "IDLE": "空闲",
            "CALLING": "呼叫中",
            "RINGING": "响铃中",
            "TALKING": "通话中",
        }
        target = self.target_user or "未选择"
        self.status_label.config(
            text=(
                f"状态: {state_map.get(self.call_state, self.call_state)} | "
                f"缓冲区: {len(self.buffer)} | 目标: {target} | 在线: {len(self.online_users)}"
            )
        )
        if self.running:
            self.root.after(400, self.update_status)

    # 关闭 socket、音频流和窗口，完成资源清理。
    def on_close(self):
        self.running = False
        self.is_recording = False

        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

        try:
            if self.play_stream is not None:
                self.play_stream.stop_stream()
                self.play_stream.close()
        except Exception:
            pass

        try:
            if self.stream_pa is not None:
                self.stream_pa.terminate()
        except Exception:
            pass

        try:
            self.audio_manager.pa.terminate()
        except Exception:
            pass

        self.root.destroy()
    
    def udp_receive_thread(self):
    # 绑定一个本地随机端口接收服务器转发回来的音频
    # 注意：UDP 是无连接的，服务器会根据你发包的来源地址回发
     while self.running:
        try:
            # 接收来自服务器转发的音频原始 PCM 数据
            data, addr = self.udp_sock.recvfrom(8192)
            if data and self.call_state == "TALKING":
                # 将收到的原始数据直接塞入播放缓冲区
                self.buffer.append(data)
        except Exception:
            continue
if __name__ == "__main__":
    root = tk.Tk()
    client = MultiFunctionClient(root)
    root.mainloop()
