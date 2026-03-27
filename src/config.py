# config.py

HOST = "127.0.0.1"
PORT = 8080
ENCODING = "utf-8"

# 音频参数
CHUNK = 1024
CHANNELS = 1
RATE = 44100
FORMAT_NAME = "paInt16"
RECORD_SECONDS = 5

# 路径
RECORDED_DIR = "data/recorded"
CLIENT_RECEIVE_DIR = "data/client_received_audio"
SERVER_SAVE_DIR = "data/server_received_audio"

# 实时语音缓冲
JITTER_BUFFER_MAXLEN = 50
JITTER_START_THRESHOLD = 5