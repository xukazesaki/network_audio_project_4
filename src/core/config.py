from pathlib import Path

import pyaudio


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONTACTS_DIR = DATA_DIR / "contacts"
RECORD_DIR = DATA_DIR / "recorded"
RECEIVE_DIR = DATA_DIR / "received"
SERVER_DATA_DIR = DATA_DIR / "server"
SERVER_RECEIVE_DIR = DATA_DIR / "server_received"

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
CONTACTS_FILE = CONTACTS_DIR / "contacts.json"
SAVED_CONTACTS_FILE = CONTACTS_DIR / "saved_contacts.txt"
SERVER_ACCOUNTS_FILE = SERVER_DATA_DIR / "accounts.json"

# Realtime voice playback tuning
JITTER_BUFFER_MAXLEN = 50
JITTER_START_THRESHOLD = 5
