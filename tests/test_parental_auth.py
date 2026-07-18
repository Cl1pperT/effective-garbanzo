import json
import os
from pathlib import Path
import tempfile
import unittest

from rfid_audio_player.parental_auth import ParentalAuth
from rfid_audio_player.web_server import WebServer


class ParentalAuthStorageTests(unittest.TestCase):
    def test_password_is_hashed_and_file_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parental_auth.json"
            auth = ParentalAuth(path)
            auth.set_password("a-strong-password")

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("a-strong-password", path.read_text(encoding="utf-8"))
            self.assertTrue(saved["password_hash"])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertTrue(ParentalAuth(path).verify("a-strong-password"))
            self.assertFalse(ParentalAuth(path).verify("wrong-password"))

            old_secret = auth.session_secret
            auth.set_password("a-different-password")
            self.assertNotEqual(auth.session_secret, old_secret)
            self.assertFalse(auth.verify("a-strong-password"))

    def test_rejects_short_password(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = ParentalAuth(Path(directory) / "parental_auth.json")
            with self.assertRaisesRegex(ValueError, "at least 8"):
                auth.set_password("short")


class FakePlayer:
    def __init__(self):
        self.settings = {"max_volume": 70}
        self.timer = None

    def get_parental_status(self):
        return self.settings

    def update_parental_settings(self, settings):
        self.settings.update(settings)
        return self.settings

    def set_sleep_timer(self, minutes):
        self.timer = minutes
        return self.settings


class FakeAuth:
    configured = True
    session_secret = "another-test-session-secret-long-enough"

    def verify(self, password):
        return password == "correct-password"


class ParentalApiTests(unittest.TestCase):
    def setUp(self):
        self.player = FakePlayer()
        app = WebServer(self.player, parental_auth=FakeAuth()).app
        self.client = app.test_client()

    def test_parental_status_remains_readable_without_login(self):
        response = self.client.get("/api/parental-controls")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["max_volume"], 70)

    def test_parental_changes_require_login(self):
        response = self.client.post("/api/parental-controls", json={"max_volume": 40})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.player.settings["max_volume"], 70)

    def test_login_unlocks_parental_settings_and_sleep_timer(self):
        login = self.client.post(
            "/api/parental-auth/login", json={"password": "correct-password"}
        )
        settings = self.client.post("/api/parental-controls", json={"max_volume": 40})
        timer = self.client.post(
            "/api/parental-controls/sleep-timer", json={"minutes": 30}
        )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(timer.status_code, 200)
        self.assertEqual(self.player.settings["max_volume"], 40)
        self.assertEqual(self.player.timer, 30)


if __name__ == "__main__":
    unittest.main()
