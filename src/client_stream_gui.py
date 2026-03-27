# client_stream_gui.py

import collections
import os
import socket
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog

from audio_core import AudioCore
from config import (
    CHUNK,
    HOST,
    JITTER_BUFFER_MAXLEN,
    JITTER_START_THRESHOLD,
    PORT,
)
from protocol import (
    make_register_packet,
    make_stream_packet,
    recv_json,
    recv_stream_bytes,
    send_bytes,
    send_json,
)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rt_gui_error.log")


def write_gui_log(text: str):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


class RealTimeChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("实时语音 GUI")
        self.root.geometry("620x650")

        self.buffer = collections.deque(maxlen=JITTER_BUFFER_MAXLEN)
        self.is_recording = False
        self.running = True

        self.username = os.environ.get("RT_GUI_USERNAME", "").strip()
        self.display_name = os.environ.get("RT_GUI_DISPLAY_NAME", self.username).strip() or self.username
        self.target_name = os.environ.get("RT_GUI_TARGET", "").strip()
        self.visible = os.environ.get("RT_GUI_VISIBLE", "0").strip() not in ("0", "false", "False")

        self.sock = None
        self.audio = None
        self.play_stream = None

        self.chat_display = scrolledtext.ScrolledText(root, state="disabled", height=22)
        self.chat_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        info_frame = tk.Frame(root)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(info_frame, text="当前目标：").pack(side=tk.LEFT)

        self.target_var = tk.StringVar(value=self.target_name)
        self.target_entry = tk.Entry(info_frame, textvariable=self.target_var, width=25)
        self.target_entry.pack(side=tk.LEFT, padx=5)

        self.btn_apply_target = tk.Button(
            info_frame,
            text="设置目标",
            command=self.apply_target
        )
        self.btn_apply_target.pack(side=tk.LEFT, padx=5)

        self.btn_mic = tk.Button(
            root,
            text="🎤 开启实时对讲",
            font=("微软雅黑", 12),
            command=self.toggle_mic,
            bg="#eeeeee"
        )
        self.btn_mic.pack(pady=10)

        self.status_label = tk.Label(root, text="网络状态: 未连接", fg="red")
        self.status_label.pack()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        try:
            self.audio = AudioCore()
            self.connect_and_register()
            self.play_stream = self.audio.get_output_stream()

            self.status_label.config(
                text=f"网络状态: 已连接，用户: {self.display_name}，目标: {self.target_name or '未设置'}",
                fg="green"
            )

            threading.Thread(target=self.receive_thread, daemon=True).start()
            threading.Thread(target=self.playback_thread, daemon=True).start()

        except Exception as e:
            write_gui_log("初始化失败:\n" + traceback.format_exc())
            try:
                messagebox.showerror("连接失败", f"无法启动实时语音 GUI:\n{e}")
            except Exception:
                pass
            self.running = False
            self.root.after(200, self.root.destroy)

    def connect_and_register(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))

        if not self.username:
            self.username = simpledialog.askstring("用户名", "请输入用户名：", parent=self.root) or ""
            self.username = self.username.strip()

        if not self.username:
            raise RuntimeError("用户名不能为空")

        send_json(
            self.sock,
            make_register_packet(
                self.username,
                visible=self.visible,
                display_name=self.display_name or self.username,
            )
        )
        meta = recv_json(self.sock)
        text = meta.get("text", "")

        if meta.get("type") != "system" or "注册成功" not in text:
            raise RuntimeError(text or "注册失败")

        self.log(f"[系统] {text}")

    def log(self, msg: str):
        self.chat_display.config(state="normal")
        self.chat_display.insert(tk.END, msg + "\n")
        self.chat_display.config(state="disabled")
        self.chat_display.see(tk.END)

    def apply_target(self):
        value = self.target_var.get().strip()
        self.target_name = value
        self.status_label.config(
            text=f"网络状态: 已连接，用户: {self.display_name}，目标: {self.target_name or '未设置'}",
            fg="green"
        )
        if value:
            self.log(f"[系统] 实时语音目标已设置为：{value}")
        else:
            self.log("[系统] 已清空实时语音目标")

    def toggle_mic(self):
        if not self.running:
            return

        if not self.target_name:
            messagebox.showwarning("提示", "请先设置实时语音目标用户")
            return

        self.is_recording = not self.is_recording
        if self.is_recording:
            self.btn_mic.config(text="🛑 停止对讲 (通话中...)", bg="#ff9999")
            threading.Thread(target=self.record_thread, daemon=True).start()
        else:
            self.btn_mic.config(text="🎤 开启实时对讲", bg="#eeeeee")

    def record_thread(self):
        input_stream = None
        try:
            input_stream = self.audio.get_input_stream()
            self.log(f"[系统] 麦克风已开启，目标：{self.target_name}")

            while self.running and self.is_recording:
                target = self.target_name.strip()
                if not target:
                    self.log("[系统] 目标用户为空，已停止发送")
                    break

                data = input_stream.read(CHUNK, exception_on_overflow=False)
                send_json(self.sock, make_stream_packet(self.display_name, target, len(data)))
                send_bytes(self.sock, data)

        except Exception as e:
            if self.running:
                self.log(f"[错误] 实时发送失败: {e}")
                write_gui_log("record_thread:\n" + traceback.format_exc())
            self.is_recording = False

        finally:
            if input_stream is not None:
                try:
                    input_stream.stop_stream()
                    input_stream.close()
                except Exception:
                    pass

            self.log("[系统] 麦克风已关闭")
            self.btn_mic.config(text="🎤 开启实时对讲", bg="#eeeeee")

    def receive_thread(self):
        while self.running:
            try:
                header = recv_json(self.sock)
                msg_type = header.get("type")

                if msg_type == "stream":
                    size = int(header.get("data_size", 0))
                    if size > 0:
                        payload = recv_stream_bytes(self.sock, size)
                        self.buffer.append(payload)

                elif msg_type == "text":
                    self.log(f"{header.get('sender', 'UNKNOWN')}: {header.get('text', '')}")

                elif msg_type == "private":
                    self.log(f"[私信][{header.get('sender', 'UNKNOWN')}] {header.get('text', '')}")

                elif msg_type == "system":
                    self.log(f"[系统] {header.get('text', '')}")

                elif msg_type == "user_list":
                    users = header.get("users", [])
                    self.log(f"[在线用户] {', '.join(users) if users else '无'}")

                elif msg_type == "audio_file":
                    sender = header.get("sender", "UNKNOWN")
                    filename = header.get("filename", "unknown.wav")
                    file_size = int(header.get("file_size", 0))
                    self.log(f"[系统] 收到音频文件 {filename}，来自 {sender}，大小 {file_size} bytes")

                else:
                    self.log(f"[系统] 未知消息：{header}")

            except Exception as e:
                if self.running:
                    self.log(f"[错误] 与服务器断开: {e}")
                    write_gui_log("receive_thread:\n" + traceback.format_exc())
                self.running = False
                break

    def playback_thread(self):
        while self.running:
            try:
                if len(self.buffer) >= JITTER_START_THRESHOLD:
                    data = self.buffer.popleft()
                    self.play_stream.write(data)
                else:
                    time.sleep(0.01)
            except Exception as e:
                if self.running:
                    self.log(f"[错误] 播放失败: {e}")
                    write_gui_log("playback_thread:\n" + traceback.format_exc())
                time.sleep(0.05)

    def on_close(self):
        self.running = False
        self.is_recording = False

        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

        try:
            if self.play_stream:
                self.play_stream.stop_stream()
                self.play_stream.close()
        except Exception:
            pass

        try:
            if self.audio:
                self.audio.terminate()
        except Exception:
            pass

        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RealTimeChatClient(root)
    root.mainloop()