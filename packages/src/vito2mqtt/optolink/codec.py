"""Data type codecs — decode/encode byte payloads for Viessmann parameters.

Each Viessmann boiler parameter has an associated *type code* (``BA``,
``IS10``, ``OO``, …) that determines how the raw bytes exchanged over the
Optolink interface map to Python values.  This module provides:

- A :class:`Codec` protocol defining the ``decode`` / ``encode`` contract.
- Concrete codec implementations for every supported type code.
- A :func:`get_codec` factory and convenience :func:`decode` / :func:`encode`
  wrappers.

**Design rationale:**  Rather than a deep class hierarchy (legacy approach),
codecs are small composable objects registered in a flat dictionary.  Numeric
codecs share a single :class:`ScaledIntCodec` parameterised at construction
time, while enum codecs share :class:`EnumCodec`.  Complex types (error sets,
timestamps, cycle times) get dedicated implementations.

See ADR-001 §3 (protocol layer) and ADR-004 (optolink protocol).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

ByteOrder = Literal["little", "big"]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CodecError(Exception):
    """Raised when a codec operation fails.

    Covers unknown type codes, unrecognised enum values, wrong payload
    lengths, and attempts to encode via a read-only codec.
    """


# ---------------------------------------------------------------------------
# Codec protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Codec(Protocol):
    """Minimal interface every data-type codec must satisfy."""

    def decode(self, data: bytes) -> Any: ...
    def encode(self, value: Any) -> bytes: ...


# ---------------------------------------------------------------------------
# CycleTimeSlot — structured value for cycle-time codec
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CycleTimeSlot:
    """A single start/stop time slot used by the cycle-time (CT) codec.

    ``None`` in any field indicates the slot is unused.
    """

    start_hour: int | None
    start_minute: int | None
    stop_hour: int | None
    stop_minute: int | None


# =========================================================================
# Concrete codecs
# =========================================================================


class EnumCodec:
    """Byte ↔ string codec backed by a lookup table.

    Parameters
    ----------
    mapping:
        ``{byte_value: label}`` dictionary.
    byteorder:
        Byte order for ``int.from_bytes`` / ``int.to_bytes``.  Default
        ``"big"`` (the common case for single-byte enums).

    **Why a shared class?**  BA, USV, OO, and RT all follow the same
    pattern: one byte maps to a human-readable label.  A generic
    ``EnumCodec`` parameterised with the specific table avoids
    duplicating nearly-identical logic (DRY principle).
    """

    def __init__(
        self, mapping: dict[int, str], *, byteorder: ByteOrder = "big"
    ) -> None:
        self._to_label = mapping
        self._to_code = {v: k for k, v in mapping.items()}
        self._byteorder = byteorder

    def decode(self, data: bytes) -> str:
        key = int.from_bytes(data, self._byteorder)
        try:
            return self._to_label[key]
        except KeyError:
            msg = f"Unknown enum value 0x{key:02X}"
            raise CodecError(msg) from None

    def encode(self, value: str) -> bytes:
        try:
            code = self._to_code[value]
        except KeyError:
            msg = f"Unknown label {value!r}"
            raise CodecError(msg) from None
        return code.to_bytes(1, self._byteorder)


class ScaledIntCodec:
    """Fixed-point integer codec with configurable scale, sign, and byte order.

    Stores ``value * divisor`` as a fixed-width integer on the wire.

    Parameters
    ----------
    divisor:
        The scaling factor.  Decoded value = raw_int / divisor.
    signed:
        Whether the on-wire integer is signed (two's complement).
    byteorder:
        ``"little"`` or ``"big"``.
    length:
        Number of bytes in the wire representation.

    **Why a shared class?**  IS10, IS100, IU2, IU10, IU3600, and IUNON all
    follow the pattern ``int.from_bytes(…) / divisor``.  Parameterising one
    class eliminates six near-identical implementations (DRY).
    """

    def __init__(
        self,
        divisor: int,
        *,
        signed: bool,
        byteorder: ByteOrder = "little",
        length: int = 2,
    ) -> None:
        self._divisor = divisor
        self._signed = signed
        self._byteorder = byteorder
        self._length = length

    def decode(self, data: bytes) -> float | int:
        if not data:
            msg = "Cannot decode empty bytes"
            raise CodecError(msg)
        raw = int.from_bytes(data, self._byteorder, signed=self._signed)
        if self._divisor == 1:
            return raw
        return raw / self._divisor

    def encode(self, value: float | int) -> bytes:
        raw = int(value * self._divisor)
        return raw.to_bytes(self._length, self._byteorder, signed=self._signed)


# ---------------------------------------------------------------------------
# Partial register codecs (read-only)
# ---------------------------------------------------------------------------


class _PR2Codec:
    """PR2 — extract the second byte of a 2-byte register as unsigned int."""

    def decode(self, data: bytes) -> int:
        return int.from_bytes(data[1:2], "little", signed=False)

    def encode(self, _value: Any) -> bytes:
        msg = "Read-only codec PR2 does not support encoding"
        raise CodecError(msg)


class _PR3Codec:
    """PR3 — extract the first byte of a 2-byte register ÷ 2."""

    def decode(self, data: bytes) -> float:
        return int.from_bytes(data[0:1], "little", signed=False) / 2

    def encode(self, _value: Any) -> bytes:
        msg = "Read-only codec PR3 does not support encoding"
        raise CodecError(msg)


# ---------------------------------------------------------------------------
# Device type codec
# ---------------------------------------------------------------------------


_DEVICE_TYPES: dict[int, str] = {
    0x2098: "V200KW2, Protokoll: KW2",
    0x2053: "GWG_VBEM, Protokoll: GWG",
    0x20CB: "VScotHO1, Protokoll: P300",
    0x2094: "V200KW1, Protokoll: KW2",
    0x209F: "V200KO1B, Protokoll: P300, KW2",
    0x204D: "V200WO1C, Protokoll: P300",
    0x204B: "Vitocal 333G, Protokoll: P300",
    0x20B8: "V333MW1, Protokoll: ",
    0x20A0: "V100GC1, Protokoll: ",
    0x20A4: "V200GW1, Protokoll: ",
    0x20C8: "VPlusHO1, Protokoll: ",
    0x20C2: "VDensHO1, Protokoll: ",
    0x2046: "V200WO1,VBC700, Protokoll: ",
    0x2047: "V200WO1,VBC700, Protokoll: ",
    0x2049: "V200WO1,VBC700, Protokoll: ",
    0x2032: "VBC550, Protokoll: ",
    0x2033: "VBC550, Protokoll: ",
    0x0000: "unknown",
}


class _DeviceTypeCodec:
    """DT — 2-byte big-endian device type code ↔ description string."""

    def __init__(self) -> None:
        self._to_name = _DEVICE_TYPES
        self._to_code = {v: k for k, v in _DEVICE_TYPES.items()}

    def decode(self, data: bytes) -> str:
        key = int.from_bytes(data, "big")
        try:
            return self._to_name[key]
        except KeyError:
            msg = f"Unknown device code 0x{key:04X}"
            raise CodecError(msg) from None

    def encode(self, value: str) -> bytes:
        try:
            code = self._to_code[value]
        except KeyError:
            msg = f"Unknown device name {value!r}"
            raise CodecError(msg) from None
        return code.to_bytes(2, "big")


# ---------------------------------------------------------------------------
# Error set codec (read-only)
# ---------------------------------------------------------------------------

_ERROR_CODES: dict[int, str] = {
    0x00: "Regelbetrieb (kein Fehler)",
    0x0F: "Wartung (fuer Reset Codieradresse 24 auf 0 stellen)",
    0x10: "Kurzschluss Aussentemperatursensor",
    0x18: "Unterbrechung Aussentemperatursensor",
    0x20: "Kurzschluss Vorlauftemperatursensor",
    0x21: "Kurzschluss Ruecklauftemperatursensor",
    0x28: "Unterbrechung Aussentemperatursensor",
    0x29: "Unterbrechung Ruecklauftemperatursensor",
    0x30: "Kurzschluss Kesseltemperatursensor",
    0x38: "Unterbrechung Kesseltemperatursensor",
    0x40: "Kurzschluss Vorlauftemperatursensor M2",
    0x42: "Unterbrechung Vorlauftemperatursensor M2",
    0x50: "Kurzschluss Speichertemperatursensor",
    0x58: "Unterbrechung Speichertemperatursensor",
    0x92: "Solar: Kurzschluss Kollektortemperatursensor",
    0x93: "Solar: Kurzschluss Sensor S3",
    0x94: "Solar: Kurzschluss Speichertemperatursensor",
    0x9A: "Solar: Unterbrechung Kollektortemperatursensor",
    0x9B: "Solar: Unterbrechung Sensor S3",
    0x9C: "Solar: Unterbrechung Speichertemperatursensor",
    0x9E: "Solar: Zu geringer bzw. kein Volumenstrom oder Temperaturwächter ausgeloest",
    0x9F: "Solar: Fehlermeldung Solarteil (siehe Solarregler)",
    0xA7: "Bedienteil defekt",
    0xB0: "Kurzschluss Abgastemperatursensor",
    0xB1: "Kommunikationsfehler Bedieneinheit",
    0xB4: "Interner Fehler (Elektronik)",
    0xB5: "Interner Fehler (Elektronik)",
    0xB6: "Ungueltige Hardwarekennung (Elektronik)",
    0xB7: "Interner Fehler (Kesselkodierstecker)",
    0xB8: "Unterbrechung Abgastemperatursensor",
    0xB9: "Interner Fehler (Dateneingabe wiederholen)",
    0xBA: "Kommunikationsfehler Erweiterungssatz fuer Mischerkreis M2",
    0xBC: "Kommunikationsfehler Fernbedienung Vitorol, Heizkreis M1",
    0xBD: "Kommunikationsfehler Fernbedienung Vitorol, Heizkreis M2",
    0xBE: "Falsche Codierung Fernbedienung Vitorol",
    0xC1: "Externe Sicherheitseinrichtung (Kessel kuehlt aus)",
    0xC2: "Kommunikationsfehler Solarregelung",
    0xC5: "Kommunikationsfehler drehzahlgeregelte Heizkreispumpe, Heizkreis M1",
    0xC6: "Kommunikationsfehler drehzahlgeregelte Heizkreispumpe, Heizkreis M2",
    0xC7: "Falsche Codierung der Heizkreispumpe",
    0xC9: "Stoermeldeeingang am Schaltmodul-V aktiv",
    0xCD: "Kommunikationsfehler Vitocom 100 (KM-BUS)",
    0xCE: "Kommunikationsfehler Schaltmodul-V",
    0xCF: "Kommunikationsfehler LON Modul",
    0xD1: "Brennerstoerung",
    0xD4: (
        "Sicherheitstemperaturbegrenzer hat ausgeloest"
        " oder Stoermeldemodul nicht richtig gesteckt"
    ),
    0xDA: "Kurzschluss Raumtemperatursensor, Heizkreis M1",
    0xDB: "Kurzschluss Raumtemperatursensor, Heizkreis M2",
    0xDD: "Unterbrechung Raumtemperatursensor, Heizkreis M1",
    0xDE: "Unterbrechung Raumtemperatursensor, Heizkreis M2",
    0xE4: "Fehler Versorgungsspannung",
    0xE5: "Interner Fehler (Ionisationselektrode)",
    0xE6: "Abgas- / Zuluftsystem verstopft",
    0xF0: "Interner Fehler (Regelung tauschen)",
    0xF1: "Abgastemperaturbegrenzer ausgeloest",
    0xF2: "Temperaturbegrenzer ausgeloest",
    0xF3: "Flammensigal beim Brennerstart bereits vorhanden",
    0xF4: "Flammensigal nicht vorhanden",
    0xF7: "Differenzdrucksensor defekt",
    0xF8: "Brennstoffventil schliesst zu spaet",
    0xF9: "Geblaesedrehzahl beim Brennerstart zu niedrig",
    0xFA: "Geblaesestillstand nicht erreicht",
    0xFD: "Fehler Gasfeuerungsautomat",
    0xFE: "Starkes Stoerfeld (EMV) in der Naehe oder Elektronik defekt",
    0xFF: "Starkes Stoerfeld (EMV) in der Naehe oder interner Fehler",
}


def _parse_bcd_timestamp(data: bytes) -> datetime:
    """Decode a BCD-encoded timestamp from 8 bytes.

    Each byte's hex representation is read as decimal digits.  For example
    ``0x20 0x24`` → year 2024.  Byte 4 (index 4) is a weekday/padding
    field that is ignored.

    Layout: ``[YY_hi, YY_lo, MM, DD, ??, HH, MM, SS]``
    """

    # Convert each byte to its "hex-as-decimal" value.
    # e.g. 0x20 → "20" → 20, 0x24 → "24" → 24  →  year = 2024
    def _bcd(b: int) -> int:
        return int(f"{b:02x}")

    year = _bcd(data[0]) * 100 + _bcd(data[1])
    month = _bcd(data[2])
    day = _bcd(data[3])
    # data[4] is weekday / padding — skipped
    hour = _bcd(data[5])
    minute = _bcd(data[6])
    second = _bcd(data[7])
    return datetime(year, month, day, hour, minute, second)


class _ErrorSetCodec:
    """ES — 9-byte error record: 1-byte error code + 8-byte BCD timestamp.

    Read-only: errors are reported by the boiler, never written.
    """

    def decode(self, data: bytes) -> tuple[str, datetime]:
        error_code = data[0]
        try:
            error_str = _ERROR_CODES[error_code]
        except KeyError:
            msg = f"Unknown error code 0x{error_code:02X}"
            raise CodecError(msg) from None
        timestamp = _parse_bcd_timestamp(data[1:9])
        return error_str, timestamp

    def encode(self, _value: Any) -> bytes:
        msg = "Read-only codec ES does not support encoding"
        raise CodecError(msg)


# ---------------------------------------------------------------------------
# System time codec (read-only)
# ---------------------------------------------------------------------------


class _SystemTimeCodec:
    """TI — 8-byte BCD system time → :class:`~datetime.datetime`.

    Layout identical to the ES timestamp: ``[YY_hi, YY_lo, MM, DD, ??, HH, MM, SS]``

    Read-only: the boiler's internal clock is not user-settable via Optolink.
    """

    def decode(self, data: bytes) -> datetime:
        return _parse_bcd_timestamp(data[0:8])

    def encode(self, _value: Any) -> bytes:
        msg = "Read-only codec TI does not support encoding"
        raise CodecError(msg)


# ---------------------------------------------------------------------------
# Cycle time codec
# ---------------------------------------------------------------------------

_CT_UNUSED_HOURS: int = 31
_CT_UNUSED_MINUTES: int = 70


class _CycleTimeCodec:
    """CT — 8-byte cycle time schedule with 4 start/stop pairs.

    Each time value is packed into 1 byte: ``(hours << 3) | (minutes // 10)``.
    Sentinel values ``hours=31`` and ``minutes=70`` indicate an unused slot.
    """

    def decode(self, data: bytes) -> list[CycleTimeSlot]:
        slots: list[CycleTimeSlot] = []
        for i in range(4):
            start_byte = data[i * 2]
            stop_byte = data[i * 2 + 1]
            slots.append(
                CycleTimeSlot(
                    start_hour=self._unpack_hours(start_byte),
                    start_minute=self._unpack_minutes(start_byte),
                    stop_hour=self._unpack_hours(stop_byte),
                    stop_minute=self._unpack_minutes(stop_byte),
                )
            )
        return slots

    def encode(self, value: list[CycleTimeSlot]) -> bytes:
        result = bytearray()
        for slot in value:
            result.append(self._pack(slot.start_hour, slot.start_minute))
            result.append(self._pack(slot.stop_hour, slot.stop_minute))
        return bytes(result)

    @staticmethod
    def _unpack_hours(b: int) -> int | None:
        hours = b >> 3
        return None if hours == _CT_UNUSED_HOURS else hours

    @staticmethod
    def _unpack_minutes(b: int) -> int | None:
        minutes = (b & 0x07) * 10
        return None if minutes == _CT_UNUSED_MINUTES else minutes

    @staticmethod
    def _pack(hours: int | None, minutes: int | None) -> int:
        h = _CT_UNUSED_HOURS if hours is None else hours
        m = _CT_UNUSED_MINUTES if minutes is None else minutes
        return (h << 3) | (m // 10)


# =========================================================================
# Codec registry
# =========================================================================

_REGISTRY: dict[str, Codec] = {
    # Enum codecs (single-byte lookups)
    "BA": EnumCodec(
        {
            0x00: "aus",
            0x01: "Red. Betrieb",
            0x02: "Normalbetrieb",
            0x03: "Heizen & WW",
            0x04: "Heizen + WW FS",
            0x05: "Abschaltbetrieb",
        }
    ),
    "USV": EnumCodec(
        {
            0x00: "UNDEF",
            0x01: "Heizen",
            0x02: "Mittelstellung",
            0x03: "Warmwasser",
        }
    ),
    "OO": EnumCodec(
        {
            0x00: "Off",
            0x01: "Manual",
            0x02: "On",
        }
    ),
    "RT": EnumCodec(
        {
            0x00: "0",
            0x01: "1",
            0x03: "2",
            0xAA: "Not OK",
        }
    ),
    # Scaled integer codecs (little-endian fixed-point)
    "IS10": ScaledIntCodec(10, signed=True),
    "IS100": ScaledIntCodec(100, signed=True),
    "IU2": ScaledIntCodec(2, signed=False),
    "IU10": ScaledIntCodec(10, signed=False),
    "IU3600": ScaledIntCodec(3600, signed=False),
    "IUNON": ScaledIntCodec(1, signed=False),
    # Partial-register codecs (read-only)
    "PR2": _PR2Codec(),
    "PR3": _PR3Codec(),
    # Complex codecs
    "DT": _DeviceTypeCodec(),
    "ES": _ErrorSetCodec(),
    "TI": _SystemTimeCodec(),
    "CT": _CycleTimeCodec(),
}


# =========================================================================
# Public API
# =========================================================================


def get_codec(type_code: str) -> Codec:
    """Look up a codec by Viessmann type code (e.g. ``"IS10"``, ``"BA"``).

    Raises :class:`CodecError` if the type code is not registered.
    """
    try:
        return _REGISTRY[type_code]
    except KeyError:
        msg = f"Unknown codec type code {type_code!r}"
        raise CodecError(msg) from None


def decode(type_code: str, data: bytes) -> Any:
    """Decode raw bytes using the codec for *type_code*.

    Convenience wrapper: ``decode("IS10", b"\\xd7\\x00")`` → ``21.5``
    """
    return get_codec(type_code).decode(data)


def encode(type_code: str, value: Any) -> bytes:
    """Encode a Python value to bytes using the codec for *type_code*.

    Convenience wrapper: ``encode("IS10", 21.5)`` → ``b"\\xd7\\x00"``
    """
    return get_codec(type_code).encode(value)
