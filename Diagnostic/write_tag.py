import time
from typing import List, Tuple

from pirc522 import RFID

from config import (
    PIN_RFID_RST,
    TAG_NDEF_START_BLOCK,
    TAG_NDEF_BLOCK_COUNT,
    TAG_AUTH_KEY,
)

BLOCK_SIZE = 16


def build_text_ndef_tlv(text: str, language: str = "en") -> bytes:
    """Builds a minimal NFC Forum NDEF text record TLV payload."""
    text_bytes = text.encode("utf-8")
    lang_bytes = language.encode("ascii")

    status = len(lang_bytes) & 0x3F  # UTF-8, language length in lower 6 bits
    payload = bytes([status]) + lang_bytes + text_bytes

    ndef_record = bytes([
        0xD1,  # MB=1, ME=1, SR=1, TNF=0x01 (Well Known)
        0x01,  # Type length
        len(payload),  # Payload length (SR so single byte)
        0x54,  # 'T' type
    ]) + payload

    return bytes([0x03, len(ndef_record)]) + ndef_record + bytes([0xFE])


def generate_block_sequence() -> List[int]:
    """Returns the absolute block numbers we will touch (trailers included)."""
    return list(range(
        TAG_NDEF_START_BLOCK,
        TAG_NDEF_START_BLOCK + TAG_NDEF_BLOCK_COUNT
    ))


def build_block_payloads(text: str) -> List[Tuple[int, bytes]]:
    """
    Returns a list of (block_number, data_bytes) tuples, skipping sector trailers.
    """
    tlv = build_text_ndef_tlv(text)
    blocks = generate_block_sequence()
    data_blocks = [b for b in blocks if (b + 1) % 4 != 0]

    buffer = bytearray(len(data_blocks) * BLOCK_SIZE)
    buffer[:len(tlv)] = tlv

    payloads = []
    offset = 0
    for block in blocks:
        if (block + 1) % 4 == 0:
            # Skip sector trailer blocks.
            continue

        chunk = buffer[offset:offset + BLOCK_SIZE]
        if len(chunk) < BLOCK_SIZE:
            chunk = chunk + bytes(BLOCK_SIZE - len(chunk))

        payloads.append((block, bytes(chunk)))
        offset += BLOCK_SIZE

    return payloads


def write_text_to_tag(text: str):
    """Waits for a tag and programs it with the provided text."""
    rfid = RFID(pin_rst=PIN_RFID_RST, bus=0, device=0)
    util = rfid.util()
    util.debug = False

    key = tuple(int(b) & 0xFF for b in TAG_AUTH_KEY[:6])
    block_payloads = build_block_payloads(text)

    print("=" * 60)
    print("RFID Text Writer")
    print("Place a tag on the reader to write the word 'Awesome'.")
    print("Press Ctrl+C to exit without writing.")
    print("=" * 60)

    try:
        while True:
            (error, _) = rfid.request()
            if error:
                time.sleep(0.1)
                continue

            (error, uid) = rfid.anticoll()
            if error:
                time.sleep(0.1)
                continue

            print(f"Tag detected UID: {''.join(map(str, uid))}")
            util.set_tag(uid)
            util.auth(rfid.auth_a, key)

            success = True
            for block, data in block_payloads:
                auth_error = util.do_auth(block, force=True)
                if auth_error:
                    print(f"Authentication failed for block {block}.")
                    success = False
                    break

                write_error = rfid.write(block, list(data))
                if write_error:
                    print(f"Write failed for block {block}.")
                    success = False
                    break

            rfid.stop_crypto()

            if success:
                print("✓ Tag programmed with text: 'Awesome'")
            else:
                print("✗ Failed to program the tag.")
            break

    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    finally:
        util.deauth()
        rfid.cleanup()


if __name__ == "__main__":
    write_text_to_tag("Awesome")
