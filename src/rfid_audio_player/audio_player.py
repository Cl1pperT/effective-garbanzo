# audio_player.py
import os
import json
import io
import math
import shutil
import struct
import subprocess
import time
import wave
from random import shuffle
from typing import Optional

import pygame
from mutagen import File as MutagenFile
from .config import (
    MEDIA_PATH, SUPPORTED_EXTENSIONS,
    DEFAULT_VOLUME
)

class AudioPlayer:
    CHARM_NOTES = {
        # Bright C-major phrases for positive actions, and a gentle descending
        # phrase for a card that needs a grown-up's help.
        "ready": ((523.25, 0.13), (659.25, 0.13), (783.99, 0.22)),
        "new_tag": ((659.25, 0.10), (880.00, 0.18)),
        "error": ((392.00, 0.14), (329.63, 0.14), (261.63, 0.24)),
    }

    def __init__(self):
        """Initializes the pygame mixer."""
        self._mixer_ready = False
        self._volume_percent = int(DEFAULT_VOLUME * 100)
        self._charm_sounds = {}
        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(DEFAULT_VOLUME)
            self._mixer_ready = True
            print("AudioPlayer initialized.")
        except pygame.error as e:
            print(f"Error initializing pygame mixer: {e}")
            print("Do you have a valid audio output device connected (e.g., USB audio)?")

        # State variables
        self.current_playlist = []  # List of full file paths
        self.current_track_index = -1
        self.paused = False
        self.playing = False
        self.current_track_duration = 0.0
        self.current_track_position = 0.0
        self.current_track_started_at: Optional[float] = None
        self.seek_supported = False
        self.parental_settings_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "parental_controls.json")
        )
        self.parental_settings = {
            "max_volume": 70,
            "buttons_locked": False,
            "rfid_locked": False,
            "seeking_locked": False,
        }
        self.sleep_timer_ends_at: Optional[float] = None
        self._load_parental_settings()
        self.set_volume(self._volume_percent)

    def _load_parental_settings(self):
        try:
            with open(self.parental_settings_path, "r", encoding="utf-8") as settings_file:
                saved = json.load(settings_file)
            if isinstance(saved, dict):
                self.parental_settings.update(saved)
        except (FileNotFoundError, OSError, ValueError):
            pass
        self.parental_settings["max_volume"] = max(
            0, min(100, int(self.parental_settings.get("max_volume", 70)))
        )
        for name in ("buttons_locked", "rfid_locked", "seeking_locked"):
            self.parental_settings[name] = bool(self.parental_settings.get(name, False))

    def update_parental_settings(self, settings: dict) -> dict:
        if "max_volume" in settings:
            self.parental_settings["max_volume"] = max(0, min(100, int(settings["max_volume"])))
        for name in ("buttons_locked", "rfid_locked", "seeking_locked"):
            if name in settings:
                self.parental_settings[name] = bool(settings[name])
        with open(self.parental_settings_path, "w", encoding="utf-8") as settings_file:
            json.dump(self.parental_settings, settings_file, indent=2)
        self.set_volume(self.get_volume())
        return self.get_parental_status()

    def get_parental_status(self) -> dict:
        remaining = 0
        if self.sleep_timer_ends_at is not None:
            remaining = max(0, round((self.sleep_timer_ends_at - time.monotonic()) / 60))
        return {**self.parental_settings, "sleep_timer_minutes": remaining}

    def set_sleep_timer(self, minutes: int) -> dict:
        minutes = max(0, min(480, int(minutes)))
        self.sleep_timer_ends_at = time.monotonic() + minutes * 60 if minutes else None
        return self.get_parental_status()

    def check_sleep_timer(self):
        if self.sleep_timer_ends_at is not None and time.monotonic() >= self.sleep_timer_ends_at:
            self.sleep_timer_ends_at = None
            self.stop()
            print("🌙 Sleep timer finished; playback stopped.")

    def set_volume(self, volume_percent: int) -> int:
        maximum = self.parental_settings["max_volume"]
        volume_percent = max(0, min(maximum, int(volume_percent)))
        self._volume_percent = volume_percent
        if self._mixer_ready:
            pygame.mixer.music.set_volume(volume_percent / 100.0)
        return volume_percent

    def get_volume(self) -> int:
        """Return the volume without requiring an initialized audio device."""
        if self._mixer_ready:
            self._volume_percent = round(pygame.mixer.music.get_volume() * 100)
        return self._volume_percent

    def load_playlist(self, key, play_tag_charm: bool = False):
        """
        Loads a new playlist based on a key.
        Returns True on success so web requests can report errors.
        """
        existing_folders = os.listdir(MEDIA_PATH)
        if key not in existing_folders:
            print(f"Error: no folder named {key} in media directory.")
            return False

        folder_path = os.path.join(MEDIA_PATH, key)

        if not os.path.isdir(folder_path):
            print(f"Error: Directory not found: {folder_path}")
            return False

        # Scan the directory (and nested Converted folder if present) for supported audio files
        self.current_playlist = self._gather_audio_files(folder_path)
        shuffle(self.current_playlist)

        if not self.current_playlist:
            print(f"No audio files found in {folder_path}")
            return False

        if play_tag_charm:
            # Stop the old story first so the cue clearly means a new one is next.
            if self._mixer_ready:
                pygame.mixer.music.stop()
            self.play_charm("new_tag", wait=True)
        
        print(f"Loaded {len(self.current_playlist)} tracks from '{key}'.")
        self.current_track_index = 0
        self._play_current_track()
        return True

    def play_charm(self, name: str, wait: bool = False) -> bool:
        """Play one of the built-in device feedback sounds."""
        if name not in self.CHARM_NOTES:
            raise ValueError(f"Unknown charm: {name}")
        if not self._mixer_ready:
            return False

        try:
            sound = self._charm_sounds.get(name)
            if sound is None:
                sound = pygame.mixer.Sound(
                    file=io.BytesIO(self._build_charm_wav(self.CHARM_NOTES[name]))
                )
                sound.set_volume(0.45)
                self._charm_sounds[name] = sound
            channel = sound.play()
            if wait and channel is not None:
                while channel.get_busy():
                    pygame.time.wait(10)
            return channel is not None
        except pygame.error as exc:
            print(f"Unable to play '{name}' charm: {exc}")
            return False

    @staticmethod
    def _build_charm_wav(notes, sample_rate: int = 22050) -> bytes:
        """Create a small mono WAV with soft attack/release envelopes."""
        frames = bytearray()
        gap_frames = int(sample_rate * 0.025)
        for frequency, duration in notes:
            note_frames = max(1, int(sample_rate * duration))
            edge_frames = max(1, int(sample_rate * 0.018))
            for index in range(note_frames):
                envelope = min(1.0, index / edge_frames, (note_frames - index) / edge_frames)
                sample = int(11000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
                frames.extend(struct.pack("<h", sample))
            frames.extend(b"\x00\x00" * gap_frames)

        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(frames)
        return output.getvalue()

    def _play_current_track(self, start_position: float = 0.0) -> bool:
        """Internal helper to load and play the current track."""
        if not self._mixer_ready:
            print("❌ Audio output is unavailable; unable to play track.")
            return False
        if not self.current_playlist or self.current_track_index == -1:
            print("No playlist loaded.")
            return False

        track_path = self.current_playlist[self.current_track_index]
        try:
            pygame.mixer.music.load(track_path)
            self.current_track_duration = self._get_track_duration(track_path)
            self.seek_supported = self._supports_seeking(track_path)
            start_position = self._clamp_position(start_position)

            if start_position > 0:
                pygame.mixer.music.play(start=start_position)
            else:
                pygame.mixer.music.play()

            self.current_track_position = start_position
            self.current_track_started_at = time.monotonic()
            self.playing = True
            self.paused = False
            track_num = self.current_track_index + 1
            total_tracks = len(self.current_playlist)
            print(f"♪ Now Playing [{track_num}/{total_tracks}]: {os.path.basename(track_path)}")
            return True
        except NotImplementedError:
            print(f"❌ Seeking is not supported for {os.path.basename(track_path)}")
            return False
        except pygame.error as e:
            print(f"❌ Error playing track {track_path}: {e}")
            return False

    def toggle_pause(self):
        """Toggles play/pause state."""
        if not self.playing:
            print("No music is currently playing. Please scan an RFID tag first.")
            return

        if self.paused:
            pygame.mixer.music.unpause()
            self.current_track_started_at = time.monotonic()
            self.paused = False
            print("▶ Resumed playback.")
        else:
            self.current_track_position = self.get_current_position()
            self.current_track_started_at = None
            pygame.mixer.music.pause()
            self.paused = True
            print("⏸ Paused.")

    def next_track(self):
        """Skips to the next track in the playlist, wrapping around."""
        if not self.current_playlist:
            print("No playlist loaded. Please scan an RFID tag first.")
            return

        # Increment index and wrap around if at the end
        self.current_track_index = (self.current_track_index + 1) % len(self.current_playlist)
        print(f"⏭ Next track ({self.current_track_index + 1}/{len(self.current_playlist)})")
        self._play_current_track()

    def prev_track(self):
        """Goes to the previous track, wrapping around."""
        if not self.current_playlist:
            print("No playlist loaded. Please scan an RFID tag first.")
            return

        # Decrement index and wrap around if at the beginning
        self.current_track_index = (self.current_track_index - 1) % len(self.current_playlist)
        print(f"⏮ Previous track ({self.current_track_index + 1}/{len(self.current_playlist)})")
        self._play_current_track()

    def volume_up(self):
        """Increases volume by 10%."""
        new_vol = self.set_volume(self.get_volume() + 10) / 100.0
        vol_bar = "█" * int(new_vol * 10) + "░" * (10 - int(new_vol * 10))
        print(f"🔊 Volume: [{vol_bar}] {int(new_vol * 100)}%")

    def volume_down(self):
        """Decreases volume by 10%."""
        new_vol = self.set_volume(self.get_volume() - 10) / 100.0
        vol_bar = "█" * int(new_vol * 10) + "░" * (10 - int(new_vol * 10))
        print(f"🔉 Volume: [{vol_bar}] {int(new_vol * 100)}%")

    def check_for_song_end(self):
        """
        To be called in the main loop. Checks if a song has
        finished and automatically plays the next one.
        """
        if self.playing and not self.paused:
            # get_busy() returns True if music is playing
            if not pygame.mixer.music.get_busy():
                # Check if we're at the last track
                is_last_track = (self.current_track_index == len(self.current_playlist) - 1)

                if is_last_track:
                    print("✓ Playlist finished.")
                    self.current_track_position = self.current_track_duration
                    self.current_track_started_at = None
                    self.playing = False
                else:
                    print("Song finished, playing next.")
                    self.next_track()

    def stop(self):
        """Stops playback and clears the playlist."""
        if self._mixer_ready:
            pygame.mixer.music.stop()
        self.current_playlist = []
        self.current_track_index = -1
        self.playing = False
        self.paused = False
        self.current_track_duration = 0.0
        self.current_track_position = 0.0
        self.current_track_started_at = None
        self.seek_supported = False

    def quit(self):
        """Shuts down the mixer."""
        if self._mixer_ready:
            pygame.mixer.quit()
            self._mixer_ready = False

    def _gather_audio_files(self, folder_path: str) -> list[str]:
        """
        Returns a list of supported audio file paths from the folder and
        its nested 'Converted' subfolder (if present).
        """
        files = []
        search_dirs = [folder_path]
        converted_dir = os.path.join(folder_path, 'Converted')
        if os.path.isdir(converted_dir):
            search_dirs.append(converted_dir)

        for directory in search_dirs:
            try:
                for entry in os.listdir(directory):
                    if any(entry.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                        files.append(os.path.join(directory, entry))
            except FileNotFoundError:
                continue
        return files

    def speak_text(self, text: str) -> bool:
        """
        Speak a short message using a system TTS engine (e.g., espeak).
        """
        tts_cmd = self._find_tts_command()
        if not tts_cmd:
            print("No TTS engine found. Install espeak or espeak-ng to enable speech.")
            return False

        was_playing = self.playing and not self.paused
        if was_playing:
            self.current_track_position = self.get_current_position()
            self.current_track_started_at = None
            pygame.mixer.music.pause()
            self.paused = True

        try:
            subprocess.run([tts_cmd, text], check=True)
            return True
        except subprocess.CalledProcessError as exc:
            print(f"Error speaking text with {tts_cmd}: {exc}")
            return False
        finally:
            if was_playing:
                pygame.mixer.music.unpause()
                self.current_track_started_at = time.monotonic()
                self.paused = False

    def _find_tts_command(self) -> Optional[str]:
        for candidate in ("espeak", "espeak-ng", "spd-say"):
            if shutil.which(candidate):
                return candidate
        return None

    def get_current_track_path(self) -> Optional[str]:
        if not self.current_playlist or self.current_track_index < 0:
            return None
        return self.current_playlist[self.current_track_index]

    def get_current_position(self) -> float:
        if self.current_track_index < 0:
            return 0.0

        position = self.current_track_position
        if not self.paused and self.current_track_started_at is not None:
            position += max(0.0, time.monotonic() - self.current_track_started_at)

        return self._clamp_position(position)

    def seek_to(self, position_seconds: float) -> tuple[bool, str]:
        if self.parental_settings["seeking_locked"]:
            return False, "Seeking has been disabled in parental controls."
        track_path = self.get_current_track_path()
        if not track_path or not self.playing and not self.paused:
            return False, "No track is currently loaded."

        if not self.seek_supported:
            return False, "Seeking is not supported for this file format."

        target_position = self._clamp_position(position_seconds)
        was_paused = self.paused

        if not self._play_current_track(target_position):
            return False, "Unable to seek within the current track."

        if was_paused:
            pygame.mixer.music.pause()
            self.paused = True
            self.current_track_position = target_position
            self.current_track_started_at = None

        return True, "Seek successful."

    def _clamp_position(self, position_seconds: float) -> float:
        if self.current_track_duration > 0:
            return max(0.0, min(position_seconds, self.current_track_duration))
        return max(0.0, position_seconds)

    def _supports_seeking(self, track_path: str) -> bool:
        extension = os.path.splitext(track_path)[1].lower()
        return extension in {".mp3", ".ogg"}

    def _get_track_duration(self, track_path: str) -> float:
        try:
            metadata = MutagenFile(track_path)
        except Exception as exc:
            print(f"Unable to read metadata for {track_path}: {exc}")
            return 0.0

        if metadata is None or not getattr(metadata, "info", None):
            return 0.0

        length = getattr(metadata.info, "length", 0.0)
        return max(0.0, float(length))
