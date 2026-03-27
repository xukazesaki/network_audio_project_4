import pyaudio

# Network settings
HOST = "10.192.28.174"
PORT = 8080
BUFFER_SIZE = 4096

# Audio settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
FORMAT_NAME = "paInt16"
CHANNELS = 1
RATE = 44100

# Storage paths
RECORD_DIR = "records"
RECEIVE_DIR = "received"
CONTACTS_FILE = "contacts.json"

# Realtime voice playback tuning
JITTER_BUFFER_MAXLEN = 50
JITTER_START_THRESHOLD = 5
