# rfid_reader.py
import time
import threading
from typing import List, Optional

from pirc522 import RFID

from .config import (
    PIN_RFID_RST,
    TAG_NDEF_START_PAGE,
    TAG_NDEF_PAGE_COUNT,
)


class Reader:
    """
    Thin wrapper around the pi-rc522 driver that handles UID polling and
    optionally extracts a text payload from the NFC NDEF message stored
    on the card.
    """

    def __init__(self):
        self.rfid: Optional[RFID] = None
        self.last_uid: Optional[str] = None
        # The main polling loop and Flask write endpoint run on different
        # threads. The RC522 driver cannot safely handle both concurrently.
        self._io_lock = threading.RLock()

        try:
            self.rfid = RFID(pin_rst=PIN_RFID_RST, bus=0, device=0)
            time.sleep(0.1)  # Allow the RC522 to stabilise.
            print("RFID reader initialised (SPI bus 0, device 0)")
        except Exception as exc:
            print(f"Error initialising RFID reader: {exc}")
            print("Ensure SPI is enabled and the RC522 is wired correctly.")

    def read_tag(self) -> tuple[Optional[str], Optional[str]]:
        """
        Polls for a new RFID tag, returning its UID string the first time
        it is presented. Once handled, that UID remains ignored until a
        different tag is presented, even if an intermediate poll misses it.
        """
        with self._io_lock:
            return self._read_tag_unlocked()

    def _read_tag_unlocked(self) -> tuple[Optional[str], Optional[str]]:
        if not self.rfid:
            return None, None

        uid_str = None
        uid_bytes: Optional[List[int]] = None

        (error, _) = self.rfid.request()
        if not error:
            (error, uid) = self.rfid.anticoll()
            if not error:
                uid_bytes = uid
                uid_str = "".join(map(str, uid))
                self.rfid.stop_crypto()

        if uid_str and uid_str != self.last_uid:
            self.last_uid = uid_str
            print(f"RFID: New tag detected with UID {uid_str}")

            text_payload = self._read_ndef_text(uid_bytes)

            return uid_str, text_payload

        return None, None

    def _read_ndef_text(self, uid_bytes: Optional[List[int]]) -> Optional[str]:
        """
        Reads NDEF TLV bytes from the configured block range and attempts
        to extract the first Well-Known Text record.
        """
        if not self.rfid or not uid_bytes or TAG_NDEF_PAGE_COUNT <= 0:
            return None

        raw_bytes = self._read_pages(
            uid_bytes,
            TAG_NDEF_START_PAGE,
            TAG_NDEF_PAGE_COUNT
        )
        if not raw_bytes:
            return None

        tlv_idx = 0
        while tlv_idx < len(raw_bytes):
            tlv_type = raw_bytes[tlv_idx]
            tlv_idx += 1

            if tlv_type == 0x00:
                continue  # NULL TLV
            if tlv_type == 0xFE:
                break  # Terminator TLV
            if tlv_idx >= len(raw_bytes):
                break

            length = raw_bytes[tlv_idx]
            tlv_idx += 1
            if length == 0xFF:
                if tlv_idx + 1 >= len(raw_bytes):
                    break
                length = (raw_bytes[tlv_idx] << 8) + raw_bytes[tlv_idx + 1]
                tlv_idx += 2

            if tlv_type == 0x03:
                ndef_message = raw_bytes[tlv_idx:tlv_idx + length]
                return self._parse_text_record(ndef_message)

            tlv_idx += length

        return None

    def _read_pages(self, uid_bytes: List[int], start_page: int, page_count: int) -> Optional[bytes]:
        """
        Reads raw bytes from NTAG-style tags (4 bytes per page, read in
        16-byte chunks). No authentication required for default tags.
        """
        if page_count <= 0:
            return None

        payload = bytearray()
        current_page = start_page
        final_page = start_page + page_count

        while current_page < final_page:
            if self.rfid is None:
                return None
            error, data = self.rfid.read(current_page)
            if error:
                print(f"RFID: Error reading starting at page {current_page}.")
                return None

            payload.extend(data)
            current_page += 4  # read command returns 4 pages (16 bytes)

        return bytes(payload[:page_count * 4])

    def _parse_text_record(self, message: bytes) -> Optional[str]:
        """
        Parses the first Well Known 'T' record contained in the NDEF message.
        """
        if not message:
            return None

        try:
            idx = 0
            header = message[idx]
            idx += 1

            sr = (header & 0x10) != 0
            il = (header & 0x08) != 0

            type_length = message[idx]
            idx += 1

            if sr:
                payload_length = message[idx]
                idx += 1
            else:
                payload_length = int.from_bytes(message[idx:idx + 4], "big")
                idx += 4

            if il:
                id_length = message[idx]
                idx += 1
            else:
                id_length = 0

            record_type = message[idx:idx + type_length]
            idx += type_length
            idx += id_length

            payload = message[idx:idx + payload_length]

            if record_type.decode("ascii", errors="ignore") != "T" or not payload:
                return None

            status = payload[0]
            is_utf16 = (status & 0x80) != 0
            lang_length = status & 0x3F

            text_bytes = payload[1 + lang_length:]
            encoding = "utf-16" if is_utf16 else "utf-8"
            text = text_bytes.decode(encoding, errors="ignore").strip()
            return text or None
        except Exception as exc:
            print(f"RFID: Failed to parse NDEF text record: {exc}")
            return None

    def write_text(self, text: str, lang_code: str = "en") -> bool:
        """
        Writes a text string to an RFID tag as an NDEF text record.

        Args:
            text: The text to write to the tag
            lang_code: The language code (default: "en")

        Returns:
            True if write was successful, False otherwise
        """
        with self._io_lock:
            return self._write_text_unlocked(text, lang_code)

    def _write_text_unlocked(self, text: str, lang_code: str = "en") -> bool:
        if not self.rfid:
            print("RFID: No RFID reader available")
            return False

        print(f"RFID: Attempting to write text: '{text}'")

        # Wait for a tag to be present
        print("RFID: Waiting for tag...")
        (error, _) = self.rfid.request()
        if error:
            print("RFID: No tag detected")
            return False

        (error, uid) = self.rfid.anticoll()
        if error:
            print("RFID: Error during anticollision")
            return False

        uid_str = "".join(map(str, uid))
        print(f"RFID: Tag detected with UID: {uid_str}")

        # Note: We do NOT call select_tag() for NTAG/Ultralight cards
        # Unlike MIFARE Classic, NTAG doesn't require selection/authentication
        # Calling select_tag() actually makes the card unresponsive for read/write

        # Create NDEF text record
        ndef_message = self._create_text_record(text, lang_code)
        if not ndef_message:
            print("RFID: Failed to create NDEF message")
            return False

        print(f"RFID: Created NDEF message ({len(ndef_message)} bytes)")
        print(f"RFID: NDEF hex: {ndef_message.hex()}")

        # Wrap in TLV structure
        tlv_data = self._create_tlv_wrapper(ndef_message)
        print(f"RFID: TLV data ({len(tlv_data)} bytes): {tlv_data.hex()}")

        # Write to tag
        success = self._write_pages(uid, tlv_data, TAG_NDEF_START_PAGE)

        self.rfid.stop_crypto()

        if success:
            print("RFID: Write successful!")
        else:
            print("RFID: Write failed")

        return success

    def _create_text_record(self, text: str, lang_code: str) -> Optional[bytes]:
        """
        Creates an NDEF text record (Well-Known Type 'T').

        Format:
        - Record header (1 byte)
        - Type length (1 byte)
        - Payload length (1 or 4 bytes)
        - Record type (1 byte: 'T')
        - Payload:
          - Status byte (1 byte: encoding + language code length)
          - Language code (variable)
          - Text (variable)
        """
        try:
            text_bytes = text.encode("utf-8")
            lang_bytes = lang_code.encode("ascii")

            # Status byte: bit 7 = encoding (0=UTF-8), bits 0-5 = lang code length
            status = len(lang_bytes) & 0x3F

            # Payload = status + lang code + text
            payload = bytes([status]) + lang_bytes + text_bytes
            payload_length = len(payload)

            # Record header: MB=1, ME=1, SR=1, TNF=1 (Well-Known)
            # MB (Message Begin) = 0x80
            # ME (Message End) = 0x40
            # SR (Short Record) = 0x10
            # TNF (Type Name Format) = 0x01 (Well-Known)
            header = 0x80 | 0x40 | 0x10 | 0x01  # 0xD1

            # Type length (1 byte for 'T')
            type_length = 1

            # Build the record
            record = bytes([header, type_length, payload_length])
            record += b'T'  # Record type
            record += payload

            print(f"RFID: Text record created - Header: 0x{header:02X}, Type: T, Payload length: {payload_length}")

            return record

        except Exception as exc:
            print(f"RFID: Error creating text record: {exc}")
            return None

    def _create_tlv_wrapper(self, ndef_message: bytes) -> bytes:
        """
        Wraps an NDEF message in TLV format for NFC Forum Type 2 tags.

        Format:
        - Type (0x03 = NDEF Message TLV)
        - Length (1 or 3 bytes)
        - Value (NDEF message)
        - Terminator (0xFE)
        """
        message_length = len(ndef_message)

        if message_length < 255:
            # Short form: Type (1) + Length (1) + Value
            tlv = bytes([0x03, message_length]) + ndef_message
        else:
            # Long form: Type (1) + 0xFF + Length (2) + Value
            tlv = bytes([0x03, 0xFF]) + message_length.to_bytes(2, 'big') + ndef_message

        # Add terminator TLV
        tlv += bytes([0xFE])

        # Pad to page boundary (4 bytes)
        padding_needed = (4 - (len(tlv) % 4)) % 4
        tlv += bytes([0x00] * padding_needed)

        return tlv

    def _write_ntag_page(self, page_num: int, data: List[int]) -> bool:
        """
        Writes 4 bytes to an NTAG page using MIFARE Ultralight WRITE command (0xA2).

        NTAG uses SINGLE-PHASE protocol (unlike MIFARE Classic's two-phase):
        Send CMD (0xA2) + Page Address + 4 Data Bytes in ONE transaction

        Args:
            page_num: Page number to write to
            data: List of 4 bytes to write

        Returns:
            True if write succeeded, False otherwise
        """
        if not self.rfid or len(data) != 4:
            return False

        # First, verify the card is still responsive by doing a read
        print(f"RFID: Verifying card is responsive by reading page {page_num}...")
        (read_error, read_data) = self.rfid.read(page_num)
        if read_error:
            print(f"RFID: Card not responsive, cannot write")
            return False
        print(f"RFID: Card responsive, current data: {read_data[:4]}")

        # MIFARE Ultralight/NTAG WRITE command (compatibility write)
        NTAG_WRITE_CMD = 0xA2

        print(f"RFID: Writing page {page_num}: {[hex(b) for b in data]}")

        # Build complete buffer: CMD + Page + 4 Data Bytes (all in one transaction)
        buf = [NTAG_WRITE_CMD, page_num]
        buf.extend(data)

        # Calculate and append CRC
        crc = self.rfid.calculate_crc(buf)
        buf.append(crc[0])
        buf.append(crc[1])

        print(f"RFID: Sending single-phase write: {[hex(b) for b in buf]}")

        # Send the complete write command in one transaction
        (error, back_data, back_length) = self.rfid.card_write(self.rfid.mode_transrec, buf)

        print(f"RFID: Response - error={error}, back_length={back_length}, back_data={back_data if not error else 'N/A'}")

        # For NTAG write, we might get a different response than MIFARE Classic
        # The ACK might be encoded differently or the response length might vary
        if back_length == 0:
            print(f"RFID: No response from card - write may have succeeded, verifying...")
            # Verify by reading back
            time.sleep(0.05)
            (verify_error, verify_data) = self.rfid.read(page_num)
            if not verify_error and verify_data[:4] == data:
                print(f"RFID: Verification successful! Data matches.")
                return True
            else:
                print(f"RFID: Verification failed. Expected {data}, got {verify_data[:4] if not verify_error else 'read error'}")
                return False

        # Check for ACK response (should be 4 bits with value 0x0A)
        if error or back_length != 4 or (back_data[0] & 0x0F) != 0x0A:
            print(f"RFID: Write failed - Expected ACK (0x0A), got {hex(back_data[0] & 0x0F) if not error and back_data else 'error'}")
            return False

        print(f"RFID: Page {page_num} write ACKed successfully!")
        return True

    def _write_pages(self, uid: List[int], data: bytes, start_page: int) -> bool:
        """
        Writes data to NTAG tag pages (4 bytes per page).

        Args:
            uid: Tag UID bytes
            data: Data to write
            start_page: Starting page number

        Returns:
            True if all writes succeeded, False otherwise
        """
        if not self.rfid:
            return False

        # Calculate number of pages needed (4 bytes per page)
        page_count = (len(data) + 3) // 4
        print(f"RFID: Writing {len(data)} bytes across {page_count} pages starting at page {start_page}")

        for i in range(page_count):
            page_num = start_page + i
            offset = i * 4
            page_data = data[offset:offset + 4]

            # Pad to 4 bytes if needed
            if len(page_data) < 4:
                page_data = page_data + bytes([0x00] * (4 - len(page_data)))

            print(f"RFID: Writing page {page_num}: {page_data.hex()} (bytes: {list(page_data)})")

            # Use NTAG-specific write method (0xA2 command for 4-byte pages)
            success = self._write_ntag_page(page_num, list(page_data))
            if not success:
                print(f"RFID: Error writing page {page_num}")
                return False

            print(f"RFID: Page {page_num} written successfully")

            # Small delay between page writes
            time.sleep(0.05)

        return True

    def cleanup(self):
        if self.rfid:
            self.rfid.cleanup()
            print("RFID reader resources cleaned up.")
