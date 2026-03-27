import pyaudio

# Network settings
HOST = "127.0.0.1"
PORT = 8080

# Audio settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
FORMAT_NAME = "paInt16"
CHANNELS = 1
RATE = 44100

# Storage paths
RECORD_DIR = "records"
RECEIVE_DIR = "received"
SERVER_RECEIVE_DIR = "server_received"
CONTACTS_FILE = "contacts.json"

# Realtime voice playback tuning
JITTER_BUFFER_MAXLEN = 50
JITTER_START_THRESHOLD = 5
