# RFID Audio Player

A Raspberry Pi-based RFID-triggered audio player with web interface for remote control and media management.

## Features

- **RFID Tag Detection**: Scan RFID tags to automatically play playlists
- **Physical Button Controls**: Hardware GPIO buttons for play/pause, volume, and track navigation
- **Web Interface**: Control your music and manage media files from any device on your network
  - Play/Pause control
  - Volume adjustment
  - Track navigation (next/previous)
  - Media file management (upload, delete)
  - Folder organization
  - Save additional Wi-Fi networks for automatic connection
  - Mobile-friendly design

## Hardware Requirements

- Raspberry Pi (tested on Pi 5)
- RC522 RFID reader module
- GPIO buttons (optional but recommended)
- Speaker or audio output device
- RFID tags (MIFARE Classic or NTAG compatible)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/wagnerrd/effective-garbanzo.git
cd effective-garbanzo
```

2. Install dependencies using uv:
```bash
uv pip install -e .
```

Or using pip:
```bash
pip install -e .
```

3. Set the parental password used to protect network and parental changes:

```bash
python scripts/set-parental-password.py
```

The password is stored as a one-way hash in a private local file. Restart the
player after changing it. Successful website logins remain valid for 15 minutes.

4. Configure your RFID-to-media mappings in `src/rfid_audio_player/config.py`:
```python
RFID_MEDIA_MAP = {
    '1364185516': 'Spiderman',  # Maps to media/Spiderman/
    '987123456': 'album-B',     # Maps to media/album-B/
}
```

5. Create your media folders and add audio files:
```bash
mkdir -p media/Spiderman
# Add .mp3, .ogg, or .wav files to the folder
```

## Usage

### Starting the Player

Run the main application:
```bash
python main.py
```

This will start:
- RFID tag reader
- GPIO button controls
- Web server (accessible at `http://tonie.local:5000` by default)

### Using the Web Interface

1. Open the player from another device on the same network:
```bash
http://tonie.local:5000
```

The `.local` name follows the player even when its IP address changes. If your
network does not support mDNS, use `hostname -I` on the Pi and open
`http://<raspberry-pi-ip>:5000` instead.

### Optional shorter URL

To remove `:5000` and use `http://tonie.local`, run the included one-time
installer from the project directory:

```bash
sudo ./scripts/install-friendly-url.sh
```

This keeps the player running as its normal user and installs a small systemd
socket proxy on port 80. The friendly URL and proxy persist across restarts.
Pass another lowercase name to the installer if desired, for example:

```bash
sudo ./scripts/install-friendly-url.sh storybox
```

2. Use the web interface to:
   - Control playback (play/pause, next/previous track)
   - Adjust volume with the slider
   - Create new media folders
   - Upload audio files
   - Delete files and folders
   - View which folders are mapped to RFID tags

### RFID Tag Usage

1. Scan an RFID tag mapped in `config.py`
2. The player will automatically load and shuffle all audio files from the corresponding folder
3. Music starts playing immediately
4. Tracks auto-advance when finished

### GPIO Button Controls

Default pin assignments (BCM numbering):
- GPIO 27: Play/Pause
- GPIO 22: Volume Up
- GPIO 23: Volume Down
- GPIO 18: Next Track
- GPIO 17: Previous Track

Customize these in `src/rfid_audio_player/config.py`.

## Configuration

Edit `src/rfid_audio_player/config.py` to customize:
- GPIO pin assignments
- RFID tag to folder mappings
- Default volume level
- Media folder path
- Supported audio formats

## File Structure

```
effective-garbanzo/
├── main.py                         # Main application entry point
├── src/
│   └── rfid_audio_player/          # Core package
│       ├── __init__.py
│       ├── audio_player.py         # Audio playback logic (pygame)
│       ├── rfid_reader.py          # RFID tag reading
│       ├── button_handler.py       # GPIO button event handlers
│       ├── web_server.py           # Flask web server
│       └── config.py               # Configuration settings
├── scripts/                        # Utility scripts
│   ├── diagnose_tag.py             # RFID tag diagnostic tool
│   └── write_tag.py                # RFID tag writing utility
├── tests/                          # Unit tests
│   ├── __init__.py
│   ├── test_audio_player.py
│   ├── test_button_handler.py
│   ├── test_config.py
│   └── test_rfid_reader.py
├── static/                         # Web interface files
│   └── index.html                  # Web UI
├── media/                          # Media files (not in git)
│   ├── Spiderman/
│   └── album-B/
├── pyproject.toml                  # Project configuration
├── requirements.txt
└── README.md

```

## API Endpoints

The web server provides the following REST API endpoints:

- `GET /api/status` - Get current player status
- `POST /api/pause` - Toggle play/pause
- `POST /api/next` - Next track
- `POST /api/prev` - Previous track
- `POST /api/volume` - Set volume (0-100)
- `GET /api/media/folders` - List media folders
- `POST /api/media/folders` - Create new folder
- `DELETE /api/media/folders/<name>` - Delete folder
- `GET /api/media/folders/<name>/files` - List files in folder
- `POST /api/media/folders/<name>/upload` - Upload file
- `DELETE /api/media/folders/<name>/files/<filename>` - Delete file
- `GET /api/networks` - List saved Wi-Fi network names
- `POST /api/networks` - Save a WPA/WPA2 Wi-Fi network
- `DELETE /api/networks` - Forget a saved Wi-Fi network

### Network setup permissions

Network setup uses NetworkManager (`nmcli`) and saves credentials in its normal
system connection store. The website never returns saved passwords. The user
running `main.py` must be authorized by NetworkManager/PolicyKit to add and
remove system connections. The friendly-URL installer configures that permission
automatically. If you do not use the friendly URL, or installed it before network
setup was added, run this once from the project directory:

```bash
sudo ./scripts/install-network-permissions.sh
```

The installed rule only grants the player user permission to modify saved system
connections, and the installer refuses to enable it until a parental password is
configured. The website requires that password before saving or forgetting a
network. Ensure NetworkManager is the active networking service.

## Supported Audio Formats

- MP3 (`.mp3`)
- Ogg Vorbis (`.ogg`)
- WAV (`.wav`)

## Running Tests

The project includes a comprehensive test suite. To run the tests:

```bash
# Run all tests
python -m unittest discover tests

# Run a specific test file
python -m unittest tests.test_audio_player

# Run with verbose output
python -m unittest discover tests -v
```

## Troubleshooting

### No audio output
- Ensure you have a valid audio device connected (USB audio or 3.5mm jack)
- Check pygame mixer initialization messages in the console

### RFID reader not working
- Verify SPI is enabled on your Raspberry Pi
- Check RFID module wiring
- Ensure the correct reset pin is configured

### Web interface not accessible
- Check that port 5000 is not blocked by firewall
- Verify your device is on the same network as the Raspberry Pi
- Check mDNS with `getent hosts tonie.local`
- Check the short-URL proxy with `systemctl status tonie-web.socket`
- Try accessing from the Pi itself: `http://localhost:5000`

## License

[Add your license here]

## Credits

Built with:
- [pygame](https://www.pygame.org/) - Audio playback
- [Flask](https://flask.palletsprojects.com/) - Web server
- [gpiozero](https://gpiozero.readthedocs.io/) - GPIO control
- [pi-rc522](https://github.com/hoffie/pi-rc522-gpiozero) - RFID reader library
