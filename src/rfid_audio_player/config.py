# config.py

# GPIO Pin definitions (BCM)
PIN_PLAY_PAUSE = 27
PIN_VOL_UP = 22
PIN_VOL_DOWN = 23
PIN_NEXT = 18
PIN_PREV = 17

# RFID Reset Pin (physical)
PIN_RFID_RST = 22

# --- Audio Player Settings ---

# Path to your media parent directory
MEDIA_PATH = "media/"

# Supported audio file extensions
SUPPORTED_EXTENSIONS = ['.mp3', '.ogg', '.wav']

# Initial volume (from 0.0 to 1.0)
DEFAULT_VOLUME = 0.5

# --- RFID Tag Writing Settings ---

# NTAG215 pages that hold the NFC Forum TLV (page 4 is the first writable page).
TAG_NDEF_START_PAGE = 4
TAG_NDEF_PAGE_COUNT = 32  # 32 pages = 128 bytes of NDEF payload space
