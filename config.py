import pyaudio

# 网络配置
HOST = '10.192.37.159'
PORT = 8080
BUFFER_SIZE = 4096

# 音频配置
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

# 存储路径
RECORD_DIR = "records"
RECEIVE_DIR = "received"