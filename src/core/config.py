from pathlib import Path

import pyaudio


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONTACTS_DIR = DATA_DIR / "contacts"
RECORD_DIR = DATA_DIR / "recorded"
RECEIVE_DIR = DATA_DIR / "received"
SERVER_DATA_DIR = DATA_DIR / "server"
SERVER_RECEIVE_DIR = DATA_DIR / "server_received"

# TCP network settings (原有服务器通信)
HOST = "10.192.38.194"
PORT = 8080
UDP_PORT = 5008

# Audio settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
FORMAT_NAME = "paInt16"
CHANNELS = 1
RATE = 44100

# Storage paths
CONTACTS_FILE = CONTACTS_DIR / "contacts.json"
SAVED_CONTACTS_FILE = CONTACTS_DIR / "saved_contacts.txt"
SERVER_ACCOUNTS_FILE = SERVER_DATA_DIR / "accounts.json"

# Realtime voice playback tuning
JITTER_BUFFER_MAXLEN = 50
JITTER_START_THRESHOLD = 5

# Multicast settings (新增)
# 224.0.0.0 ~ 239.255.255.255 为组播地址范围
# 这里选一个实验室/局域网内可用的自定义组播地址
MCAST_GRP = "239.255.10.10"
MCAST_PORT = 5007
MCAST_TTL = 2
MCAST_LOOPBACK = False
MCAST_BUFFER_SIZE = 4096
