# main.py
import socket
import subprocess
import time
from typing import Optional

from src.rfid_audio_player import AudioPlayer, Reader, ButtonControls, WebServer


def _get_ip_address() -> Optional[str]:
    ip_address = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip_address = sock.getsockname()[0]
    except OSError:
        ip_address = None

    if not ip_address or ip_address.startswith("127."):
        try:
            output = subprocess.check_output(["hostname", "-I"], text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            output = ""
        candidates = [item for item in output.split() if item and not item.startswith("127.")]
        if candidates:
            ip_address = candidates[0]

    return ip_address


def _speak_ip_address(player: AudioPlayer) -> None:
    ip_address = _get_ip_address()
    if not ip_address:
        print("Unable to determine IP address.")
        player.speak_text("I could not determine the IP address.")
        return

    print(f"IP address detected: {ip_address}")
    spoken_ip = ip_address.replace(".", " dot ")
    player.speak_text(f"My IP address is {spoken_ip}.")

if __name__ == "__main__":
    """
    Main application entry point.
    Initializes all components and runs the main loop.
    """
    
    # Initialize components
    player = None
    reader = None
    buttons = None
    web_server = None

    try:
        # 1. Initialize the core components
        print("🎵 Initializing PhonieBox Minimal...")
        player = AudioPlayer()
        reader = Reader()

        # 2. Initialize the button handler and pass it the player
        #    This automatically links all button events.
        buttons = ButtonControls(player)

        # 3. Initialize and start the web server
        web_server = WebServer(player, reader)
        web_server.run(host='0.0.0.0', port=5000)

        print("\n" + "="*50)
        print("  🎵 PhonieBox Minimal is RUNNING 🎵")
        print("="*50)
        print("📡 Waiting for an RFID tag...")
        print("🎮 Button controls are active")
        print("🛑 Press Ctrl+C to exit")
        print("="*50 + "\n")
        player.play_charm("ready", wait=True)

        # 4. Start the main application loop
        while True:
            # Check for a new RFID tag.
            # The reader.read_tag() method is smart and will
            # only return a UID once when a *new* tag is presented.
            # Do not touch the RC522 while parental controls have disabled
            # card reads. Web-based card writing remains available.
            if player.parental_settings["rfid_locked"]:
                uid, text = None, None
            else:
                uid, text = reader.read_tag()
            
            if uid is not None:
                print(f"Main loop detected new UID: {uid}, text {text}")
                if text is None:
                    print("No text found on tag.")
                    player.play_charm("error")
                else:
                    tag_text = text.strip()
                    if tag_text.upper() == "IP":
                        player.play_charm("new_tag", wait=True)
                        _speak_ip_address(player)
                    else:
                        if not player.load_playlist(tag_text, play_tag_charm=True):
                            player.play_charm("error")
            
            # Check if the current song has finished playing.
            # This is necessary for auto-playing the next track.
            player.check_for_song_end()
            player.check_sleep_timer()

            # Poll every 100ms. This is idle time, preventing
            # the loop from using 100% CPU.
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down... (Ctrl+C pressed)")

    finally:
        # 5. Clean up resources
        print("\n🧹 Cleaning up resources...")
        if player:
            player.quit()
            print("  ✓ Audio player shut down")
        if reader:
            reader.cleanup()
            print("  ✓ RFID reader cleaned up")
        if buttons:
            buttons.cleanup()
        print("\n👋 Goodbye!")
