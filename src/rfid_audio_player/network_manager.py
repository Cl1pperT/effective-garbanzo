"""Manage saved Wi-Fi profiles through NetworkManager's command-line client."""

from __future__ import annotations

import os
import re
import subprocess
import uuid


class NetworkManagerError(RuntimeError):
    """A user-facing NetworkManager operation failure."""


class NetworkManager:
    WIFI_TYPES = {"wifi", "802-11-wireless"}
    UUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
        r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    )

    def __init__(self, executable: str = "nmcli"):
        self.executable = executable

    @staticmethod
    def _error_detail(exc: subprocess.CalledProcessError) -> str:
        detail = (exc.stderr or exc.stdout or "NetworkManager rejected the request").strip()
        permission_markers = ("insufficient privileges", "not authorized", "not permitted")
        if any(marker in detail.casefold() for marker in permission_markers):
            return (
                "Network changes are not authorized. On the player, run "
                "sudo ./scripts/install-network-permissions.sh, then try again."
            )
        return detail

    def _run(self, *args: str) -> str:
        env = {**os.environ, "LC_ALL": "C"}
        try:
            result = subprocess.run(
                [self.executable, *args],
                check=True,
                capture_output=True,
                text=True,
                env=env,
                timeout=20,
            )
        except FileNotFoundError as exc:
            raise NetworkManagerError(
                "NetworkManager is not installed (nmcli was not found)."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise NetworkManagerError("NetworkManager did not respond in time.") from exc
        except subprocess.CalledProcessError as exc:
            raise NetworkManagerError(self._error_detail(exc)) from exc
        return result.stdout.strip()

    def _connection_rows(self, active: bool = False) -> list[tuple[str, str]]:
        args = ["-t", "--escape", "no", "-f", "UUID,TYPE", "connection", "show"]
        if active:
            args.append("--active")
        output = self._run(*args)
        rows = []
        for line in output.splitlines():
            connection_uuid, separator, connection_type = line.partition(":")
            if separator and connection_type in self.WIFI_TYPES:
                rows.append((connection_uuid, connection_type))
        return rows

    def _ssid(self, connection_uuid: str) -> str:
        return self._run(
            "--get-values", "802-11-wireless.ssid", "connection", "show", connection_uuid
        )

    def list_networks(self) -> list[dict]:
        active_uuids = {row[0] for row in self._connection_rows(active=True)}
        networks = []
        for connection_uuid, _ in self._connection_rows():
            ssid = self._ssid(connection_uuid)
            if not ssid:
                continue
            networks.append({
                "id": connection_uuid,
                "name": ssid,
                "active": connection_uuid in active_uuids,
            })
        return sorted(networks, key=lambda item: (not item["active"], item["name"].casefold()))

    @staticmethod
    def _validate_credentials(ssid: str, password: str) -> tuple[str, str]:
        if not isinstance(ssid, str) or not isinstance(password, str):
            raise ValueError("Network name and password must be text.")
        ssid = ssid.strip()
        if not ssid:
            raise ValueError("Network name is required.")
        if "\x00" in ssid or "\n" in ssid or "\r" in ssid:
            raise ValueError("Network name contains unsupported characters.")
        if len(ssid.encode("utf-8")) > 32:
            raise ValueError("Network name must be 32 bytes or fewer.")
        valid_password = 8 <= len(password) <= 63 or (
            len(password) == 64 and all(char in "0123456789abcdefABCDEF" for char in password)
        )
        if not valid_password:
            raise ValueError("Wi-Fi password must be 8–63 characters (or a 64-digit hex key).")
        return ssid, password

    def add_network(self, ssid: str, password: str) -> dict:
        ssid, password = self._validate_credentials(ssid, password)
        if any(network["name"] == ssid for network in self.list_networks()):
            raise ValueError(f'Network "{ssid}" is already saved.')

        connection_uuid = str(uuid.uuid4())
        try:
            self._run(
                "connection", "add", "type", "wifi", "ifname", "*",
                "con-name", ssid, "connection.uuid", connection_uuid, "ssid", ssid,
            )
            self._run(
                "connection", "modify", connection_uuid,
                "connection.autoconnect", "yes",
                "802-11-wireless-security.key-mgmt", "wpa-psk",
                "802-11-wireless-security.psk", password,
            )
        except NetworkManagerError:
            # Avoid leaving a half-configured open profile if the security update fails.
            try:
                self._run("connection", "delete", connection_uuid)
            except NetworkManagerError:
                pass
            raise
        return {"id": connection_uuid, "name": ssid, "active": False}

    def delete_network(self, connection_uuid: str) -> None:
        if not isinstance(connection_uuid, str) or not self.UUID_PATTERN.fullmatch(connection_uuid):
            raise ValueError("Invalid network profile ID.")
        matching = [network for network in self.list_networks() if network["id"] == connection_uuid]
        if not matching:
            raise ValueError("Saved network was not found.")
        if matching[0]["active"]:
            raise ValueError("The network currently in use cannot be removed.")
        self._run("connection", "delete", connection_uuid)
