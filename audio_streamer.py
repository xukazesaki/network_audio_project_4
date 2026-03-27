# audio_streamer.py
import pyaudio
from config import CHUNK, FORMAT_NAME, CHANNELS, RATE

class AudioEngine:
    # 创建一个用于流式输入输出的 PyAudio 封装。
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.format = getattr(pyaudio, FORMAT_NAME)
        self.is_streaming = False

    def get_input_stream(self):
        """开启麦克风输入流"""
        return self.pa.open(
            format=self.format,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )

    def get_output_stream(self):
        """开启扬声器输出流"""
        return self.pa.open(
            format=self.format,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK
        )

    def terminate(self):
        self.pa.terminate()
