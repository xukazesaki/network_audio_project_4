# config.py

from pathlib import Path

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096
ENCODING = "utf-8"

# 音频参数
CHUNK = 1024
FORMAT_NAME = "paInt16"
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

RECORDED_DIR = DATA_DIR / "recorded"
CLIENT_RECEIVE_DIR = DATA_DIR / "client_received_audio"
SERVER_SAVE_DIR = DATA_DIR / "server_received_audio"
RECEIVED_AUDIO_DIR = DATA_DIR / "received_audio"