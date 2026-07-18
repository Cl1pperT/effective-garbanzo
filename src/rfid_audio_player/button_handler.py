# button_handler.py
from gpiozero import Button
from datetime import datetime
from .config import (
    PIN_PLAY_PAUSE,
    PIN_VOL_UP,
    PIN_VOL_DOWN,
    PIN_NEXT,
    PIN_PREV
)

class ButtonControls:
    """
    Manages all GPIO button inputs and links them to
    audio player actions.
    """
    def __init__(self, audio_player):
        """
        Initializes all buttons.

        Assumes buttons are wired between the GPIO pin and a GND pin.

        Args:
            audio_player: An instance of the AudioPlayer class.
        """
        # Store reference to audio player
        self.audio_player = audio_player

        # We pass the audio_player object in so we can link
        # its methods directly to the button press events.

        # Play/Pause Button
        self.btn_play_pause = Button(PIN_PLAY_PAUSE, pull_up=True, bounce_time=0.1)
        self.btn_play_pause.when_pressed = self._on_play_pause

        # Volume Up Button
        self.btn_vol_up = Button(PIN_VOL_UP, pull_up=True, bounce_time=0.1)
        self.btn_vol_up.when_pressed = self._on_volume_up

        # Volume Down Button
        self.btn_vol_down = Button(PIN_VOL_DOWN, pull_up=True, bounce_time=0.1)
        self.btn_vol_down.when_pressed = self._on_volume_down

        # Next Track Button
        self.btn_next = Button(PIN_NEXT, pull_up=True, bounce_time=0.1)
        self.btn_next.when_pressed = self._on_next_track

        # Previous Track Button
        self.btn_prev = Button(PIN_PREV, pull_up=True, bounce_time=0.1)
        self.btn_prev.when_pressed = self._on_prev_track

        print("✓ Button controls initialized and linked to audio player.")
        print(f"  - Play/Pause: GPIO {PIN_PLAY_PAUSE}")
        print(f"  - Volume Up:  GPIO {PIN_VOL_UP}")
        print(f"  - Volume Down: GPIO {PIN_VOL_DOWN}")
        print(f"  - Next Track: GPIO {PIN_NEXT}")
        print(f"  - Prev Track: GPIO {PIN_PREV}")

        # Note: 'bounce_time=0.1' (100ms) is added to prevent
        # a single physical press from registering multiple times.

    def _on_play_pause(self, button):
        """Handler for play/pause button press."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Button pressed: Play/Pause (GPIO {PIN_PLAY_PAUSE})")
            if self._press_allowed():
                self.audio_player.toggle_pause()
        except Exception as e:
            print(f"❌ Error handling play/pause: {e}")

    def _on_volume_up(self, button):
        """Handler for volume up button press."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Button pressed: Volume Up (GPIO {PIN_VOL_UP})")
            if self._press_allowed():
                self.audio_player.volume_up()
        except Exception as e:
            print(f"❌ Error handling volume up: {e}")

    def _on_volume_down(self, button):
        """Handler for volume down button press."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Button pressed: Volume Down (GPIO {PIN_VOL_DOWN})")
            if self._press_allowed():
                self.audio_player.volume_down()
        except Exception as e:
            print(f"❌ Error handling volume down: {e}")

    def _on_next_track(self, button):
        """Handler for next track button press."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Button pressed: Next Track (GPIO {PIN_NEXT})")
            if self._press_allowed():
                self.audio_player.next_track()
        except Exception as e:
            print(f"❌ Error handling next track: {e}")

    def _on_prev_track(self, button):
        """Handler for previous track button press."""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Button pressed: Previous Track (GPIO {PIN_PREV})")
            if self._press_allowed():
                self.audio_player.prev_track()
        except Exception as e:
            print(f"❌ Error handling previous track: {e}")

    def cleanup(self):
        """Clean up GPIO resources."""
        try:
            self.btn_play_pause.close()
            self.btn_vol_up.close()
            self.btn_vol_down.close()
            self.btn_next.close()
            self.btn_prev.close()
            print("✓ Button controls cleaned up.")
        except Exception as e:
            print(f"Warning: Error during button cleanup: {e}")

    def _press_allowed(self):
        if self.audio_player.parental_settings["buttons_locked"]:
            print("🔒 Physical button press ignored (parental lock is on).")
            return False
        return True
