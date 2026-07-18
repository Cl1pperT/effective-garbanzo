import subprocess
import unittest
from unittest.mock import patch

from rfid_audio_player.network_manager import NetworkManager, NetworkManagerError
from rfid_audio_player.web_server import WebServer


class FakeNetworkManager(NetworkManager):
    def __init__(self, responses=None):
        super().__init__()
        self.responses = list(responses or [])
        self.calls = []

    def _run(self, *args):
        self.calls.append(args)
        response = self.responses.pop(0) if self.responses else ""
        if isinstance(response, Exception):
            raise response
        return response


class NetworkManagerTests(unittest.TestCase):
    def test_lists_wifi_only_and_marks_active_network(self):
        manager = FakeNetworkManager([
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa:wifi",
            (
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa:wifi\n"
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb:ethernet\n"
                "cccccccc-cccc-4ccc-8ccc-cccccccccccc:wifi"
            ),
            "Home",
            "Grandparents",
        ])

        self.assertEqual(manager.list_networks(), [
            {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "name": "Home", "active": True},
            {"id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "name": "Grandparents", "active": False},
        ])

    def test_rejects_invalid_credentials_before_calling_nmcli(self):
        manager = FakeNetworkManager()
        for name, password in [("", "longenough"), ("Cafe", "short"), ("x" * 33, "longenough")]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    manager.add_network(name, password)
        self.assertEqual(manager.calls, [])

    def test_rejects_duplicate_ssid(self):
        manager = FakeNetworkManager([
            "", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa:wifi", "Home"
        ])
        with self.assertRaisesRegex(ValueError, "already saved"):
            manager.add_network("Home", "a-secure-password")

    @patch("rfid_audio_player.network_manager.uuid.uuid4")
    def test_adds_autoconnecting_secured_profile(self, uuid4):
        uuid4.return_value = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        manager = FakeNetworkManager(["", "", "", ""])

        result = manager.add_network("Road Trip", "a-secure-password")

        self.assertEqual(result["name"], "Road Trip")
        self.assertIn((
            "connection", "modify", "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            "connection.autoconnect", "yes",
            "802-11-wireless-security.key-mgmt", "wpa-psk",
            "802-11-wireless-security.psk", "a-secure-password",
        ), manager.calls)

    @patch("rfid_audio_player.network_manager.uuid.uuid4")
    def test_removes_partial_profile_when_security_setup_fails(self, uuid4):
        uuid4.return_value = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        failure = NetworkManagerError("not authorized")
        manager = FakeNetworkManager(["", "", "", failure, ""])

        with self.assertRaises(NetworkManagerError):
            manager.add_network("Road Trip", "a-secure-password")

        self.assertEqual(manager.calls[-1], (
            "connection", "delete", "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        ))

    def test_does_not_delete_active_network(self):
        connection_uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        manager = FakeNetworkManager([
            f"{connection_uuid}:wifi", f"{connection_uuid}:wifi", "Home"
        ])

        with self.assertRaisesRegex(ValueError, "currently in use"):
            manager.delete_network(connection_uuid)
        self.assertFalse(any(call[:2] == ("connection", "delete") for call in manager.calls))

    @patch("rfid_audio_player.network_manager.subprocess.run")
    def test_nmcli_permission_errors_include_setup_command(self, run):
        run.side_effect = subprocess.CalledProcessError(
            10, ["nmcli"], stderr="Error: not authorized"
        )
        with self.assertRaisesRegex(NetworkManagerError, "install-network-permissions.sh"):
            NetworkManager().list_networks()

    @patch("rfid_audio_player.network_manager.subprocess.run")
    def test_other_nmcli_errors_are_preserved(self, run):
        run.side_effect = subprocess.CalledProcessError(
            10, ["nmcli"], stderr="Error: NetworkManager is not running"
        )
        with self.assertRaisesRegex(NetworkManagerError, "NetworkManager is not running"):
            NetworkManager().list_networks()


class FakeWebNetworkManager:
    def __init__(self):
        self.networks = [{
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "name": "Home",
            "active": True,
        }]
        self.added = None
        self.deleted = None

    def list_networks(self):
        return self.networks

    def add_network(self, name, password):
        self.added = (name, password)
        return {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "name": name, "active": False}

    def delete_network(self, connection_uuid):
        self.deleted = connection_uuid


class FakeParentalAuth:
    configured = True
    session_secret = "a-test-session-secret-that-is-long-enough"

    def verify(self, password):
        return password == "correct-password"


class NetworkApiTests(unittest.TestCase):
    def setUp(self):
        self.manager = FakeWebNetworkManager()
        self.server = WebServer(
            object(), network_manager=self.manager, parental_auth=FakeParentalAuth()
        )
        self.client = self.server.app.test_client()
        response = self.client.post(
            "/api/parental-auth/login", json={"password": "correct-password"}
        )
        self.assertEqual(response.status_code, 200)

    def test_get_returns_names_without_credentials(self):
        response = self.client.get("/api/networks")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"networks": self.manager.networks})
        self.assertNotIn("password", response.get_data(as_text=True))

    def test_post_passes_password_but_does_not_return_it(self):
        response = self.client.post(
            "/api/networks", json={"name": "Travel", "password": "a-secure-password"}
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.manager.added, ("Travel", "a-secure-password"))
        self.assertNotIn("a-secure-password", response.get_data(as_text=True))

    def test_post_requires_parental_login(self):
        client = self.server.app.test_client()
        response = client.post(
            "/api/networks", json={"name": "Travel", "password": "a-secure-password"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "parental_password_required")
        self.assertIsNone(self.manager.added)

    def test_incorrect_parental_password_does_not_unlock(self):
        client = self.server.app.test_client()
        login = client.post(
            "/api/parental-auth/login", json={"password": "wrong-password"}
        )
        save = client.post(
            "/api/networks", json={"name": "Travel", "password": "a-secure-password"}
        )

        self.assertEqual(login.status_code, 401)
        self.assertEqual(save.status_code, 401)

    def test_delete_uses_opaque_profile_id(self):
        connection_uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        response = self.client.delete("/api/networks", json={"id": connection_uuid})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.manager.deleted, connection_uuid)


if __name__ == "__main__":
    unittest.main()
