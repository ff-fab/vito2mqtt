"""P300 telegram framing — encode and decode Viessmann Optolink telegrams.

The P300 protocol uses a binary telegram format for communication with
Viessmann boiler control units over the Optolink serial interface.

Telegram wire format::

    START(0x41) | LENGTH | TYPE | MODE | ADDR_HI
    | ADDR_LO | DATA_LEN | [PAYLOAD] | CHECKSUM

Where:
- ``START`` is always ``0x41``
- ``LENGTH`` is the number of bytes from TYPE through DATA_LEN (+ payload if present)
- ``TYPE`` distinguishes request (0x00), response (0x01), and error (0x03)
- ``MODE`` distinguishes read (0x01), write (0x02), and function call (0x07)
- ``ADDR`` is a 16-bit big-endian address identifying the boiler parameter
- ``DATA_LEN`` is the number of payload bytes (0 for read requests)
- ``CHECKSUM`` is ``sum(bytes[1:]) % 256``

See ADR-004 for design rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

START_BYTE: int = 0x41
"""P300 telegram start marker."""

# Minimum telegram size: START + LENGTH + TYPE + MODE + ADDR(2) + DATA_LEN + CHECKSUM
_MIN_TELEGRAM_LENGTH: int = 8


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TelegramType(IntEnum):
    """P300 telegram type field."""

    REQUEST = 0x00
    RESPONSE = 0x01
    ERROR = 0x03


class TelegramMode(IntEnum):
    """P300 telegram mode field."""

    READ = 0x01
    WRITE = 0x02
    FUNCTION_CALL = 0x07


# ---------------------------------------------------------------------------
# Telegram value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Telegram:
    """Immutable representation of a P300 telegram.

    Attributes:
        type: Request, Response, or Error.
        mode: Read, Write, or FunctionCall.
        address: 16-bit boiler parameter address.
        data: Payload bytes (empty for read requests and write acks).
    """

    type: TelegramType
    mode: TelegramMode
    address: int
    data: bytes


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------


def checksum(data: bytes) -> int:
    """Compute the P300 checksum: sum of all bytes, modulo 256.

    Args:
        data: Byte sequence to checksum (everything after START, before CHECKSUM).

    Returns:
        Single-byte checksum value (0–255).
    """
    return sum(data) % 256


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


def encode_read_request(*, address: int, data_length: int) -> bytes:
    """Encode a P300 read request telegram.

    Args:
        address: 16-bit boiler parameter address.
        data_length: Number of bytes to read from the address.

    Returns:
        Complete telegram as bytes, ready to send over serial.
    """
    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF

    # Body: TYPE + MODE + ADDR_HI + ADDR_LO + DATA_LEN
    body = bytes(
        [
            TelegramType.REQUEST,
            TelegramMode.READ,
            addr_hi,
            addr_lo,
            data_length,
        ]
    )
    length = len(body)
    payload = bytes([length]) + body
    cs = checksum(payload)
    return bytes([START_BYTE]) + payload + bytes([cs])


def encode_write_request(*, address: int, data: bytes) -> bytes:
    """Encode a P300 write request telegram.

    Args:
        address: 16-bit boiler parameter address.
        data: Payload bytes to write to the address.

    Returns:
        Complete telegram as bytes, ready to send over serial.
    """
    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF

    # Body: TYPE + MODE + ADDR_HI + ADDR_LO + DATA_LEN + PAYLOAD
    body = (
        bytes(
            [
                TelegramType.REQUEST,
                TelegramMode.WRITE,
                addr_hi,
                addr_lo,
                len(data),
            ]
        )
        + data
    )
    length = len(body)
    payload = bytes([length]) + body
    cs = checksum(payload)
    return bytes([START_BYTE]) + payload + bytes([cs])


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


def decode_telegram(raw: bytes) -> Telegram:
    """Decode a raw P300 telegram from bytes.

    Args:
        raw: Complete telegram bytes including START and CHECKSUM.

    Returns:
        Parsed ``Telegram`` instance.

    Raises:
        ValueError: If the telegram is malformed (wrong start byte, bad
            checksum, or truncated).
    """
    if len(raw) < _MIN_TELEGRAM_LENGTH:
        msg = (
            f"Telegram too short: got {len(raw)} bytes, "
            f"minimum is {_MIN_TELEGRAM_LENGTH}"
        )
        raise ValueError(msg)

    if raw[0] != START_BYTE:
        msg = f"Invalid start byte: expected 0x{START_BYTE:02X}, got 0x{raw[0]:02X}"
        raise ValueError(msg)

    # Everything between START (exclusive) and CHECKSUM (exclusive)
    body = raw[1:-1]
    expected_cs = checksum(body)
    actual_cs = raw[-1]
    if actual_cs != expected_cs:
        msg = f"Checksum mismatch: expected 0x{expected_cs:02X}, got 0x{actual_cs:02X}"
        raise ValueError(msg)

    # Parse fields
    # body[0] = length, body[1] = type, body[2] = mode,
    # body[3] = addr_hi, body[4] = addr_lo, body[5] = data_len
    telegram_type = TelegramType(body[1])
    telegram_mode = TelegramMode(body[2])
    address = (body[3] << 8) | body[4]
    data_len = body[5]
    data = body[6 : 6 + data_len]

    return Telegram(
        type=telegram_type,
        mode=telegram_mode,
        address=address,
        data=data,
    )
