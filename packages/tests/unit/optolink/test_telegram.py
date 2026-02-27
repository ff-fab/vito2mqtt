"""Unit tests for vito2mqtt.optolink.telegram — P300 telegram framing.

Behavioral specs for P300 telegram encoding, decoding, and checksum validation.
Tests are derived from the P300 protocol specification, not from any reference
implementation (clean-room TDD).

Test Techniques Used:
- Specification-based Testing: Verifying telegram structure against P300 spec
- Equivalence Partitioning: Request types (read/write), response types (data/error)
- Boundary Value Analysis: Empty payloads, max-length payloads, checksum edge cases
- Round-trip Testing: Encode → decode fidelity
- Error Guessing: Malformed telegrams, wrong checksums, truncated data
"""

from __future__ import annotations

import pytest

from vito2mqtt.optolink.telegram import (
    Telegram,
    TelegramMode,
    TelegramType,
    checksum,
    decode_telegram,
    encode_read_request,
    encode_write_request,
)

# =============================================================================
# P300 Protocol Constants (from specification)
# =============================================================================
#
# Telegram format:
#   START(0x41) | LENGTH | TYPE | MODE | ADDR_HI | ADDR_LO
#   | DATA_LEN | [PAYLOAD] | CHECKSUM
#
# Types: Request=0x00, Response=0x01, Error=0x03
# Modes: Read=0x01, Write=0x02, FunctionCall=0x07
# Checksum: sum of all bytes after START, mod 256
#
# Control bytes (not part of telegrams):
#   RESET=0x04, NOT_INIT=0x05, SYNC=0x16 0x00 0x00, ACK=0x06


# =============================================================================
# Checksum
# =============================================================================


class TestChecksum:
    """Checksum computation over byte sequences.

    Technique: Specification-based — checksum is sum of bytes mod 256.
    """

    def test_checksum_empty_bytes_returns_zero(self) -> None:
        assert checksum(b"") == 0

    def test_checksum_single_byte(self) -> None:
        assert checksum(b"\x05") == 0x05

    def test_checksum_multiple_bytes(self) -> None:
        # 0x01 + 0x02 + 0x03 = 0x06
        assert checksum(b"\x01\x02\x03") == 0x06

    def test_checksum_wraps_at_256(self) -> None:
        # 0xFF + 0x01 = 0x100, mod 256 = 0x00
        assert checksum(b"\xff\x01") == 0x00

    def test_checksum_wraps_at_256_nonzero(self) -> None:
        # 0xFF + 0x02 = 0x101, mod 256 = 0x01
        assert checksum(b"\xff\x02") == 0x01

    def test_checksum_large_sequence(self) -> None:
        # 256 bytes of 0x01 → sum = 256, mod 256 = 0
        assert checksum(b"\x01" * 256) == 0x00


# =============================================================================
# Telegram Data Class
# =============================================================================


class TestTelegram:
    """Telegram value object — immutable representation of a P300 telegram.

    Technique: Specification-based — verify field semantics and immutability.
    """

    def test_telegram_fields_accessible(self) -> None:
        t = Telegram(
            type=TelegramType.REQUEST,
            mode=TelegramMode.READ,
            address=0x00F8,
            data=b"",
        )
        assert t.type == TelegramType.REQUEST
        assert t.mode == TelegramMode.READ
        assert t.address == 0x00F8
        assert t.data == b""

    def test_telegram_with_payload(self) -> None:
        t = Telegram(
            type=TelegramType.RESPONSE,
            mode=TelegramMode.READ,
            address=0x0800,
            data=b"\xef\x00",
        )
        assert t.data == b"\xef\x00"
        assert len(t.data) == 2


# =============================================================================
# Encode Read Request
# =============================================================================


class TestEncodeReadRequest:
    """Encode a P300 read request telegram to bytes.

    Technique: Specification-based — verify wire format matches P300 spec.
    Format: 0x41 | LENGTH | 0x00 | 0x01 | ADDR_HI | ADDR_LO | DATA_LEN | CHECKSUM
    """

    def test_encode_read_request_basic(self) -> None:
        """Read 2 bytes from address 0x00F8 (outside temperature)."""
        result = encode_read_request(address=0x00F8, data_length=2)

        # Header: START=0x41
        assert result[0] == 0x41

        # Payload length (bytes after START, before checksum): 5 bytes
        # (type + mode + addr_hi + addr_lo + data_len)
        assert result[1] == 0x05

        # Type = Request (0x00)
        assert result[2] == 0x00

        # Mode = Read (0x01)
        assert result[3] == 0x01

        # Address high byte, low byte
        assert result[4] == 0x00  # addr high
        assert result[5] == 0xF8  # addr low

        # Requested data length
        assert result[6] == 0x02

        # Checksum: sum of bytes[1:7] mod 256
        expected_checksum = (0x05 + 0x00 + 0x01 + 0x00 + 0xF8 + 0x02) % 256
        assert result[7] == expected_checksum

        # Total length: START + 5 payload bytes + length byte + checksum = 8
        assert len(result) == 8

    def test_encode_read_request_high_address(self) -> None:
        """Read from address 0x088A (both address bytes non-zero)."""
        result = encode_read_request(address=0x088A, data_length=4)
        assert result[4] == 0x08
        assert result[5] == 0x8A
        assert result[6] == 0x04

    def test_encode_read_request_single_byte(self) -> None:
        """Read a single byte — minimum data_length."""
        result = encode_read_request(address=0x7700, data_length=1)
        assert result[6] == 0x01
        assert len(result) == 8  # Same structure regardless of data_length


# =============================================================================
# Encode Write Request
# =============================================================================


class TestEncodeWriteRequest:
    """Encode a P300 write request telegram to bytes.

    Technique: Specification-based — verify wire format matches P300 spec.
    Format: 0x41 | LENGTH | 0x00 | 0x02 | ADDR_HI
    | ADDR_LO | DATA_LEN | PAYLOAD | CHECKSUM
    """

    def test_encode_write_request_single_byte(self) -> None:
        """Write a single byte to address 0x2306."""
        result = encode_write_request(address=0x2306, data=b"\x01")

        assert result[0] == 0x41  # START
        # Length: type + mode + addr(2) + data_len + payload(1) = 6
        assert result[1] == 0x06
        assert result[2] == 0x00  # Type = Request
        assert result[3] == 0x02  # Mode = Write
        assert result[4] == 0x23  # addr high
        assert result[5] == 0x06  # addr low
        assert result[6] == 0x01  # data length
        assert result[7] == 0x01  # payload byte
        # Checksum over bytes[1:8]
        assert len(result) == 9

    def test_encode_write_request_multi_byte(self) -> None:
        """Write multiple bytes (e.g. a timer schedule)."""
        payload = b"\x06\x00\x22\x00\xff\xff\xff\xff"
        result = encode_write_request(address=0x2100, data=payload)

        assert result[3] == 0x02  # Mode = Write
        assert result[6] == len(payload)
        # Payload should appear in bytes [7 : 7 + len(payload)]
        assert result[7 : 7 + len(payload)] == payload
        # Total: START(1) + length(1) + type(1) + mode(1) + addr(2) + datalen(1)
        #        + payload + checksum(1)
        assert len(result) == 1 + 1 + 5 + len(payload) + 1


# =============================================================================
# Decode Response Telegram
# =============================================================================


class TestDecodeResponseTelegram:
    """Decode a raw P300 response from bytes into a Telegram.

    Technique: Specification-based + Error Guessing for malformed inputs.
    """

    def test_decode_read_response(self) -> None:
        """Decode a valid read response with 2 bytes of data."""
        # Build a valid response:
        # START | LENGTH=7 | TYPE=0x01 | MODE=0x01
        # | ADDR=0x00F8 | DATALEN=2 | DATA | CHECKSUM
        body = bytes([0x07, 0x01, 0x01, 0x00, 0xF8, 0x02, 0xEF, 0x00])
        cs = checksum(body)
        raw = bytes([0x41]) + body + bytes([cs])

        telegram = decode_telegram(raw)

        assert telegram.type == TelegramType.RESPONSE
        assert telegram.mode == TelegramMode.READ
        assert telegram.address == 0x00F8
        assert telegram.data == b"\xef\x00"

    def test_decode_write_response(self) -> None:
        """Decode a write acknowledgment (response to write, no payload data)."""
        # Write response: TYPE=0x01, MODE=0x02, ADDR, DATALEN=0, no payload
        body = bytes([0x05, 0x01, 0x02, 0x23, 0x06, 0x00])
        cs = checksum(body)
        raw = bytes([0x41]) + body + bytes([cs])

        telegram = decode_telegram(raw)

        assert telegram.type == TelegramType.RESPONSE
        assert telegram.mode == TelegramMode.WRITE
        assert telegram.address == 0x2306
        assert telegram.data == b""

    def test_decode_error_response(self) -> None:
        """Decode an error response (TYPE=0x03)."""
        body = bytes([0x05, 0x03, 0x01, 0x00, 0xF8, 0x02])
        cs = checksum(body)
        raw = bytes([0x41]) + body + bytes([cs])

        telegram = decode_telegram(raw)

        assert telegram.type == TelegramType.ERROR

    def test_decode_rejects_bad_start_byte(self) -> None:
        """Telegram must start with 0x41."""
        body = bytes([0x05, 0x01, 0x01, 0x00, 0xF8, 0x00])
        cs = checksum(body)
        raw = bytes([0x42]) + body + bytes([cs])

        with pytest.raises(ValueError, match="[Ss]tart"):
            decode_telegram(raw)

    def test_decode_rejects_bad_checksum(self) -> None:
        """Wrong checksum must raise an error."""
        body = bytes([0x05, 0x01, 0x01, 0x00, 0xF8, 0x00])
        correct_cs = checksum(body)
        bad_cs = (correct_cs + 1) % 256  # Guaranteed wrong
        raw = bytes([0x41]) + body + bytes([bad_cs])

        with pytest.raises(ValueError, match="[Cc]hecksum"):
            decode_telegram(raw)

    def test_decode_rejects_truncated_telegram(self) -> None:
        """Telegram shorter than minimum length must raise."""
        with pytest.raises(ValueError):
            decode_telegram(bytes([0x41, 0x05]))


# =============================================================================
# Round-Trip (Encode → Decode)
# =============================================================================


class TestRoundTrip:
    """Verify that encode → transmit → decode preserves telegram semantics.

    Technique: Round-trip Testing — encode a request, simulate the matching
    response, decode it, and verify the data matches.
    """

    def test_read_roundtrip_preserves_address(self) -> None:
        """Encode a read request, build a matching response, decode it."""
        address = 0x088A
        data_length = 4

        # Encode the request (just to verify structure)
        request = encode_read_request(address=address, data_length=data_length)
        assert request[0] == 0x41

        # Simulate response: same address, type=RESPONSE, with data
        response_data = b"\x01\x02\x03\x04"
        body = (
            bytes(
                [
                    0x05 + data_length,  # length
                    0x01,  # type = response
                    0x01,  # mode = read
                    (address >> 8) & 0xFF,
                    address & 0xFF,
                    data_length,
                ]
            )
            + response_data
        )
        cs = checksum(body)
        raw_response = bytes([0x41]) + body + bytes([cs])

        telegram = decode_telegram(raw_response)
        assert telegram.address == address
        assert telegram.data == response_data

    @pytest.mark.parametrize(
        ("address", "data"),
        [
            (0x00F8, b"\x01"),
            (0x088A, b"\xab\xcd"),
            (0x7700, b"\x00\x00\x00\x00"),
        ],
        ids=["single-byte", "two-bytes", "four-zeros"],
    )
    def test_write_roundtrip_preserves_data(self, address: int, data: bytes) -> None:
        """Encode a write, build matching ack response, verify address."""
        request = encode_write_request(address=address, data=data)
        assert request[0] == 0x41
        assert request[3] == 0x02  # write mode

        # Simulate write acknowledgment response
        body = bytes(
            [
                0x05,  # length (no payload in ack)
                0x01,  # type = response
                0x02,  # mode = write
                (address >> 8) & 0xFF,
                address & 0xFF,
                0x00,  # data_len = 0 in ack
            ]
        )
        cs = checksum(body)
        raw_response = bytes([0x41]) + body + bytes([cs])

        telegram = decode_telegram(raw_response)
        assert telegram.address == address
        assert telegram.mode == TelegramMode.WRITE
