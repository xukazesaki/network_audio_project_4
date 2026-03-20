# audio_utils.py

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
            "未安装 pyaudio。请先执行:\n"
            "pip install pyaudio\n"
            "如果 Windows 安装失败，可尝试:\n"
            "pip install pipwin\n"
            "pipwin install pyaudio"
        )


def get_pyaudio_format():
    ensure_pyaudio()
    return getattr(pyaudio, FORMAT_NAME)


def record_wav(output_path: str, seconds: int = RECORD_SECONDS) -> None:
    ensure_pyaudio()

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=get_pyaudio_format(),
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    print(f"开始录音，时长 {seconds} 秒 ...")
    frames = []

    for _ in range(int(RATE / CHUNK * seconds)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    print("录音结束")

    stream.stop_stream()
    stream.close()

    sample_width = pa.get_sample_size(get_pyaudio_format())
    pa.terminate()

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_width)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))


def play_wav(file_path: str) -> None:
    ensure_pyaudio()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    wf = wave.open(file_path, "rb")
    pa = pyaudio.PyAudio()

    stream = pa.open(
        format=pa.get_format_from_width(wf.getsampwidth()),
        channels=wf.getnchannels(),
        rate=wf.getframerate(),
        output=True,
    )

    print(f"开始播放: {file_path}")
    data = wf.readframes(CHUNK)
    while data:
        stream.write(data)
        data = wf.readframes(CHUNK)

    stream.stop_stream()
    stream.close()
    wf.close()
    pa.terminate()
    print("播放结束")

def record_until_enter(output_path: str):
    ensure_pyaudio()

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=get_pyaudio_format(),
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    print("按 Enter 开始录音...")
    input()

    print("正在录音... 再按 Enter 结束")

    frames = []
    recording = True

    import threading

    def wait_stop():
        nonlocal recording
        input()
        recording = False

    stop_thread = threading.Thread(target=wait_stop)
    stop_thread.start()

    while recording:
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    print("录音结束")

    stream.stop_stream()
    stream.close()

    sample_width = pa.get_sample_size(get_pyaudio_format())
    pa.terminate()

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_width)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))