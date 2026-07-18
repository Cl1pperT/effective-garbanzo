#!/usr/bin/env python3
"""Interactively create or replace the web parental password."""

from getpass import getpass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rfid_audio_player.parental_auth import ParentalAuth  # noqa: E402


def main() -> int:
    auth = ParentalAuth()
    first = getpass("New parental password (at least 8 characters): ")
    second = getpass("Confirm parental password: ")
    if first != second:
        print("Passwords did not match.", file=sys.stderr)
        return 1
    try:
        auth.set_password(first)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Parental password saved. Restart the player to activate it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

