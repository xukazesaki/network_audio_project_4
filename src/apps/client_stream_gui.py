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
from src.core.protocol import recv_packet, send_packet


class MultiFunctionClient:
    # 初始化客户端主窗口、认证状态以及网络和音频组件。
    def __init__(self, root):
        self.root = root
        self.root.title("综合音频终端")
        self.root.geometry("900x820")

        self.sock = None
        self.running = True
        self.is_recording = False
        self.buffer = collections.deque(maxlen=JITTER_BUFFER_MAXLEN)
        self.audio_manager = AudioManager()

        self.my_name = None
        self.target_user = None
        self.online_users = []
        self.friends = {}
        self.user_index_map = {}
        self.play_stream = None
        self.stream_pa = None

        self.call_state = "IDLE"
        self.call_peer = None
        self.ringing_from = None

        self._build_ui()

        if not self.connect_and_auth():
            self.running = False
            self.root.after(0, self.root.destroy)
            return

        self.refresh_user_listbox()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(400, self.update_status)

    # 创建在线用户列表、聊天区、通话控制和媒体控制的界面布局。
    def _build_ui(self):
        self.status_label = tk.Label(
            self.root,
            text="状态: 未登录 | 缓冲区: 0 | 目标: 未选择 | 在线: 0",
            fg="blue",
            font=("Arial", 10, "bold"),
        )
        self.status_label.pack(pady=6)

        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        sidebar = tk.Frame(body)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(sidebar, text="在线用户").pack(anchor="w")
        self.user_listbox = tk.Listbox(sidebar, width=28, height=24, bg="#f8f8f8")
        self.user_listbox.pack(fill=tk.Y, expand=True)
        self.user_listbox.bind("<<ListboxSelect>>", self.on_user_select)
        self.user_listbox.bind("<Double-Button-1>", self.on_user_select)

        tk.Button(sidebar, text="设为当前目标", command=self.on_user_select).pack(
            fill=tk.X, pady=(8, 4)
        )

        self.friend_placeholder = tk.Label(
            sidebar,
            text="好友电话本将切换为服务端数据",
            fg="gray",
            justify=tk.LEFT,
            wraplength=180,
        )
        self.friend_placeholder.pack(fill=tk.X, pady=(8, 0))

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

        tk.Button(button_row, text="发送文字", command=self.send_text, width=10).pack(
            side=tk.LEFT, padx=2
        )
        tk.Button(button_row, text="发送文件", command=self.send_file, width=10).pack(
            side=tk.LEFT, padx=2
        )
        tk.Button(
            button_row,
            text="录音 5 秒发送",
            command=self.send_offline_voice,
            width=14,
        ).pack(side=tk.LEFT, padx=2)

        call_row = tk.Frame(controls)
        call_row.pack(fill=tk.X, pady=(8, 0))
        tk.Button(call_row, text="呼叫", command=self.call_user, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(call_row, text="接听", command=self.accept_call, width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(call_row, text="挂断", command=self.hangup, width=10).pack(side=tk.LEFT, padx=2)

        self.auto_call_label = tk.Label(
            controls,
            text="已启用：接通后自动开始实时语音",
            fg="green",
            font=("Arial", 10, "bold"),
        )
        self.auto_call_label.pack(fill=tk.X, pady=8)

    # 建立连接并完成注册/登录；认证成功后再启动后台线程。
    def connect_and_auth(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
        except Exception as e:
            messagebox.showerror("错误", f"连接服务器失败: {e}")
            return False

        try:
            auth_user = self.run_auth_flow()
            if not auth_user:
                return False

            self.my_name = auth_user
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
            return True
        except Exception as e:
            messagebox.showerror("错误", f"认证失败: {e}")
            return False

    # 弹出认证操作选择框，明确区分注册、登录和退出。
    def choose_auth_action(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("登录或注册")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        result = {"action": None}

        tk.Label(
            dialog,
            text="请选择接下来的操作",
            font=("Arial", 11, "bold"),
            padx=24,
            pady=16,
        ).pack()

        button_row = tk.Frame(dialog, padx=16, pady=12)
        button_row.pack()

        def select(action):
            result["action"] = action
            dialog.destroy()

        tk.Button(button_row, text="注册", width=10, command=lambda: select("register")).pack(
            side=tk.LEFT, padx=6
        )
        tk.Button(button_row, text="登录", width=10, command=lambda: select("login")).pack(
            side=tk.LEFT, padx=6
        )
        tk.Button(button_row, text="退出", width=10, command=lambda: select(None)).pack(
            side=tk.LEFT, padx=6
        )

        dialog.protocol("WM_DELETE_WINDOW", lambda: select(None))
        dialog.update_idletasks()

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        dlg_w = dialog.winfo_width()
        dlg_h = dialog.winfo_height()
        pos_x = root_x + max((root_w - dlg_w) // 2, 0)
        pos_y = root_y + max((root_h - dlg_h) // 2, 0)
        dialog.geometry(f"+{pos_x}+{pos_y}")

        self.root.wait_window(dialog)
        return result["action"]

    # 运行启动时的认证流程；注册成功后返回到认证选择，不自动登录。
    def run_auth_flow(self):
        while self.running:
            action = self.choose_auth_action()
            if action is None:
                return None

            username = simpledialog.askstring(
                "用户名",
                "请输入用户名：",
                parent=self.root,
            )
            if username is None:
                continue

            username = username.strip()
            if not username:
                messagebox.showwarning("提示", "用户名不能为空")
                continue

            if action == "register":
                register_ok = self.try_register(username)
                if not register_ok:
                    continue
                continue

            login_ok = self.try_login(username)
            if login_ok:
                return username

        return None

    # 发送注册请求，并根据服务端回包给出提示。
    def try_register(self, username):
        send_packet(self.sock, "register", username)
        header, _ = recv_packet(self.sock)
        if not header:
            messagebox.showerror("错误", "注册时与服务器断开连接")
            return False

        msg_type = header.get("type")
        if msg_type == "register_ok":
            messagebox.showinfo("提示", f"注册成功：{username}")
            self._consume_auth_text_tip()
            return True

        if msg_type == "register_error":
            code = header.get("code", "unknown_error")
            messagebox.showwarning("注册失败", self.format_auth_error(code))
            self._consume_auth_text_tip()
            return False

        self._handle_unexpected_auth_packet(header)
        return False

    # 发送登录请求，并根据服务端回包判断是否进入主界面。
    def try_login(self, username):
        send_packet(self.sock, "login", username)
        header, _ = recv_packet(self.sock)
        if not header:
            messagebox.showerror("错误", "登录时与服务器断开连接")
            return False

        msg_type = header.get("type")
        if msg_type == "login_ok":
            return True

        if msg_type == "login_error":
            code = header.get("code", "unknown_error")
            messagebox.showwarning("登录失败", self.format_auth_error(code))
            self._consume_auth_text_tip()
            return False

        self._handle_unexpected_auth_packet(header)
        return False

    # 将服务端认证错误码转换为更易理解的中文提示。
    def format_auth_error(self, code):
        code_map = {
            "empty_username": "用户名不能为空。",
            "username_taken": "该用户名已存在，请换一个用户名。",
            "user_not_found": "该用户尚未注册，请先注册。",
            "already_authenticated": "当前客户端已经登录，不能再次登录其他账户。",
        }
        return code_map.get(code, f"操作失败：{code}")

    # 吃掉认证失败后服务端附带的 text 提示包，避免进入主线程后重复显示。
    def _consume_auth_text_tip(self):
        try:
            header, _ = recv_packet(self.sock)
        except Exception:
            return

        if not header:
            return

        if header.get("type") != "text":
            self._handle_unexpected_auth_packet(header)

    # 处理认证阶段收到的非预期回包。
    def _handle_unexpected_auth_packet(self, header):
        msg_type = header.get("type", "unknown")
        if msg_type == "text":
            messagebox.showinfo("服务器消息", header.get("msg", ""))
            return
        messagebox.showwarning("提示", f"收到未预期的认证响应：{msg_type}")

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

    # 根据在线用户和预留的好友数据刷新左侧列表。
    def refresh_user_listbox(self):
        self.user_listbox.delete(0, tk.END)
        self.user_index_map.clear()

        names = sorted(set(self.online_users) | set(self.friends.keys()))
        insert_index = 0
        for username in names:
            if username == self.my_name:
                continue

            online = username in self.online_users
            prefix = "在线" if online else "离线"
            label = f"[{prefix}] {username}"

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

    # 在通话建立后自动开启实时语音发送。
    def start_realtime_voice(self):
        if self.call_state != "TALKING":
            return
        if self.is_recording:
            return
        if not self.call_peer:
            return

        self.is_recording = True
        threading.Thread(target=self.record_stream_thread, daemon=True).start()
        self.log(f"[系统] 已开始与 {self.call_peer} 实时通话", align="center")

    # 接听当前正在响铃的来电，并开始实时语音。
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
        self.start_realtime_voice()

    # 挂断当前进行中或等待中的通话。
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
        self.buffer.clear()

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
            while self.running and self.is_recording and self.call_state == "TALKING" and self.call_peer:
                data = stream.read(CHUNK, exception_on_overflow=False)
                send_packet(self.sock, "stream", self.my_name, {"target": self.call_peer}, data)
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
                self.start_realtime_voice()
            elif msg_type == "hangup":
                self.safe_log(f"[系统] {sender} 已挂断", align="center")
                self._reset_call_state()
            elif msg_type in {"register_ok", "register_error", "login_ok", "login_error"}:
                continue
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
        login_state = self.my_name or "未登录"
        self.status_label.config(
            text=(
                f"状态: {state_map.get(self.call_state, login_state)} | "
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


if __name__ == "__main__":
    root = tk.Tk()
    client = MultiFunctionClient(root)
    root.mainloop()
