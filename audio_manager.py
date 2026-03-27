import pyaudio
import wave
import os
from config import *

class AudioManager:
    # 创建一个共享的 PyAudio 实例，供录音和播放使用。
    def __init__(self):
        self.pa = pyaudio.PyAudio()

    # 录制固定时长的原始 PCM 音频数据。
    def record_audio(self, duration=5):
        stream = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        frames = []
        for _ in range(0, int(RATE / CHUNK * duration)):
            frames.append(stream.read(CHUNK))
        stream.stop_stream()
        stream.close()
        return b"".join(frames)

    # 立即播放一段原始 PCM 音频数据。
    def play_audio(self, audio_data):
        stream = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)
        stream.write(audio_data)
        stream.stop_stream()
        stream.close()

    # 将原始 PCM 音频保存为 wav 文件。
    def save_wav(self, filename, data):
        if not os.path.exists(RECORD_DIR): os.makedirs(RECORD_DIR)
        path = os.path.join(RECORD_DIR, filename)
        wf = wave.open(path, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.pa.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(data)
        wf.close()
        return path
