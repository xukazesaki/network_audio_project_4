# audio_core.py

import os
import wave

try:
    import pyaudio
except ImportError:
    pyaudio = None

from config import CHUNK, CHANNELS, RATE, RECORD_SECONDS, FORMAT_NAME


def ensure_pyaudio():
    if pyaudio is None:
        raise RuntimeError(
            "未安装 pyaudio。\n"
            "请先执行：\n"
            "pip install pyaudio\n"
            "如果 Windows 安装失败，可尝试：\n"
            "pip install pipwin\n"
            "pipwin install pyaudio"
        )


class AudioCore:
    def __init__(self):
        ensure_pyaudio()
        self.pa = pyaudio.PyAudio()
        self.format = getattr(pyaudio, FORMAT_NAME)

    def terminate(self):
        try:
            self.pa.terminate()
        except Exception:
            pass

    def record_audio(self, duration: int = RECORD_SECONDS) -> bytes:
        """
        录制固定时长原始 PCM 音频。
        """
        stream = self.pa.open(
            format=self.format,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        frames = []
        try:
            for _ in range(int(RATE / CHUNK * duration)):
                frames.append(stream.read(CHUNK, exception_on_overflow=False))
        finally:
            stream.stop_stream()
            stream.close()
        return b"".join(frames)

    def save_wav(self, file_path: str, data: bytes):
        """
        将原始 PCM 数据保存为 wav。
        """
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.pa.get_sample_size(self.format))
            wf.setframerate(RATE)
            wf.writeframes(data)

    def play_audio_bytes(self, audio_data: bytes):
        """
        播放原始 PCM 数据。
        """
        stream = self.pa.open(
            format=self.format,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )
        try:
            stream.write(audio_data)
        finally:
            stream.stop_stream()
            stream.close()

    def play_wav(self, file_path: str):
        """
        播放 wav 文件。
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        wf = wave.open(file_path, "rb")
        stream = self.pa.open(
            format=self.pa.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
        )

        try:
            data = wf.readframes(CHUNK)
            while data:
                stream.write(data)
                data = wf.readframes(CHUNK)
        finally:
            stream.stop_stream()
            stream.close()
            wf.close()

    def get_input_stream(self):
        return self.pa.open(
            format=self.format,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

    def get_output_stream(self):
        return self.pa.open(
            format=self.format,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )