"""Unit tests for vito2mqtt.optolink.codec — data type codecs.

Behavioral specs for encoding and decoding byte payloads exchanged with the
Viessmann boiler control unit.  Each Viessmann parameter has an associated
'type code' (BA, IS10, OO, …) that governs how raw bytes map to Python values.

Test Techniques Used:
- Specification-based Testing: Input→output pairs derived from protocol docs
- Equivalence Partitioning: Numeric vs. enum vs. complex multi-byte codecs
- Boundary Value Analysis: Min/max values, zero, negative, scaling edge cases
- Round-trip Testing: encode(decode(raw)) == raw, decode(encode(val)) == val
- Error Guessing: Unknown enum codes, wrong-length payloads, read-only codecs

See ADR-001 for the layered architecture rationale.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from vito2mqtt.optolink.codec import (
    CodecError,
    CycleTimeSlot,
    decode,
    encode,
    get_codec,
)

# =============================================================================
# Codec Registry / Factory
# =============================================================================


class TestGetCodec:
    """Verify the codec registry returns a codec for every supported type code."""

    KNOWN_CODES = [
        "BA",
        "USV",
        "OO",
        "RT",
        "IS10",
        "IS100",
        "IU2",
        "IU10",
        "IU3600",
        "IUNON",
        "DT",
        "ES",
        "TI",
        "CT",
        "PR2",
        "PR3",
    ]

    @pytest.mark.parametrize("code", KNOWN_CODES)
    def test_returns_codec_for_known_code(self, code: str) -> None:
        """Every supported type code resolves to a non-None codec.

        Technique: Equivalence Partitioning — one representative per type.
        """
        codec = get_codec(code)
        assert codec is not None

    def test_raises_for_unknown_code(self) -> None:
        """Unknown type codes raise CodecError.

        Technique: Error Guessing — invalid input.
        """
        with pytest.raises(CodecError, match="Unknown.*XYZZY"):
            get_codec("XYZZY")


# =============================================================================
# Top-level helpers: decode() / encode()
# =============================================================================


class TestDecodeEncode:
    """Convenience wrappers that combine codec lookup + operation."""

    def test_decode_delegates_to_codec(self) -> None:
        """decode(type_code, data) looks up the codec and decodes."""
        result = decode("IUNON", b"\x2a\x00")
        assert result == 42

    def test_encode_delegates_to_codec(self) -> None:
        """encode(type_code, value) looks up the codec and encodes."""
        result = encode("IUNON", 42)
        assert result == b"\x2a\x00"


# =============================================================================
# Enum Codecs — single-byte lookup tables
# =============================================================================


class TestOperatingModeCodec:
    """BA (Betriebsart) — operating mode enum, 1 byte.

    Technique: Decision Table — each code maps to exactly one label.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00", "aus"),
            (b"\x01", "Red. Betrieb"),
            (b"\x02", "Normalbetrieb"),
            (b"\x03", "Heizen & WW"),
            (b"\x04", "Heizen + WW FS"),
            (b"\x05", "Abschaltbetrieb"),
        ],
        ids=[
            "off",
            "reduced",
            "normal",
            "heating+dhw",
            "heating+dhw-fs",
            "shutdown",
        ],
    )
    def test_decode(self, raw: bytes, expected: str) -> None:
        assert decode("BA", raw) == expected

    @pytest.mark.parametrize(
        ("label", "expected_raw"),
        [
            ("aus", b"\x00"),
            ("Normalbetrieb", b"\x02"),
            ("Abschaltbetrieb", b"\x05"),
        ],
        ids=["off", "normal", "shutdown"],
    )
    def test_encode(self, label: str, expected_raw: bytes) -> None:
        assert encode("BA", label) == expected_raw

    def test_round_trip(self) -> None:
        """Technique: Round-trip Testing."""
        raw = b"\x03"
        assert encode("BA", decode("BA", raw)) == raw

    def test_decode_unknown_code_raises(self) -> None:
        """Technique: Error Guessing — byte value outside known set."""
        with pytest.raises(CodecError):
            decode("BA", b"\xff")


class TestSwitchValveCodec:
    """USV (Umschaltventil) — switch valve enum, 1 byte.

    Technique: Decision Table.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00", "UNDEF"),
            (b"\x01", "Heizen"),
            (b"\x02", "Mittelstellung"),
            (b"\x03", "Warmwasser"),
        ],
        ids=["undef", "heating", "middle", "dhw"],
    )
    def test_decode(self, raw: bytes, expected: str) -> None:
        assert decode("USV", raw) == expected

    @pytest.mark.parametrize(
        ("label", "expected_raw"),
        [
            ("Heizen", b"\x01"),
            ("Warmwasser", b"\x03"),
        ],
        ids=["heating", "dhw"],
    )
    def test_encode(self, label: str, expected_raw: bytes) -> None:
        assert encode("USV", label) == expected_raw

    def test_decode_unknown_raises(self) -> None:
        with pytest.raises(CodecError):
            decode("USV", b"\xff")


class TestOnOffCodec:
    """OO (On/Off) — 1 byte enum.

    Technique: Decision Table.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00", "Off"),
            (b"\x01", "Manual"),
            (b"\x02", "On"),
        ],
        ids=["off", "manual", "on"],
    )
    def test_decode(self, raw: bytes, expected: str) -> None:
        assert decode("OO", raw) == expected

    @pytest.mark.parametrize(
        ("label", "expected_raw"),
        [
            ("Off", b"\x00"),
            ("On", b"\x02"),
        ],
        ids=["off", "on"],
    )
    def test_encode(self, label: str, expected_raw: bytes) -> None:
        assert encode("OO", label) == expected_raw

    def test_round_trip(self) -> None:
        raw = b"\x01"
        assert encode("OO", decode("OO", raw)) == raw

    def test_decode_unknown_raises(self) -> None:
        with pytest.raises(CodecError):
            decode("OO", b"\xab")


class TestReturnStatusCodec:
    """RT (ReturnStatus) — 1 byte enum.

    Technique: Decision Table.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00", "0"),
            (b"\x01", "1"),
            (b"\x03", "2"),
            (b"\xaa", "Not OK"),
        ],
        ids=["status-0", "status-1", "status-2", "not-ok"],
    )
    def test_decode(self, raw: bytes, expected: str) -> None:
        assert decode("RT", raw) == expected

    @pytest.mark.parametrize(
        ("label", "expected_raw"),
        [
            ("0", b"\x00"),
            ("Not OK", b"\xaa"),
        ],
        ids=["status-0", "not-ok"],
    )
    def test_encode(self, label: str, expected_raw: bytes) -> None:
        assert encode("RT", label) == expected_raw


# =============================================================================
# Scaled Integer Codecs — little-endian with fixed-point scaling
# =============================================================================


class TestIS10Codec:
    """IS10 — signed integer ÷ 10, little-endian.

    Technique: Boundary Value Analysis + Round-trip.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0.0),
            (b"\xe8\x03", 100.0),  # 1000 / 10
            (b"\xd7\x00", 21.5),  # 215 / 10
            (b"\x18\xfc", -100.0),  # -1000 / 10  (two's complement)
            (b"\x01\x00", 0.1),  # 1 / 10
            (b"\xff\xff", -0.1),  # -1 / 10
        ],
        ids=["zero", "100.0", "21.5", "-100.0", "0.1", "-0.1"],
    )
    def test_decode(self, raw: bytes, expected: float) -> None:
        result = decode("IS10", raw)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected_raw"),
        [
            (0.0, b"\x00\x00"),
            (21.5, b"\xd7\x00"),
            (-100.0, b"\x18\xfc"),
        ],
        ids=["zero", "21.5", "-100.0"],
    )
    def test_encode(self, value: float, expected_raw: bytes) -> None:
        assert encode("IS10", value) == expected_raw

    def test_round_trip(self) -> None:
        raw = b"\xd7\x00"
        assert encode("IS10", decode("IS10", raw)) == raw


class TestIS100Codec:
    """IS100 — signed integer ÷ 100, little-endian.

    Technique: Boundary Value Analysis.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0.0),
            (b"\xe8\x03", 10.0),  # 1000 / 100
            (b"\x18\xfc", -10.0),  # -1000 / 100
            (b"\x01\x00", 0.01),  # 1 / 100
        ],
        ids=["zero", "10.0", "-10.0", "0.01"],
    )
    def test_decode(self, raw: bytes, expected: float) -> None:
        result = decode("IS100", raw)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected_raw"),
        [
            (10.0, b"\xe8\x03"),
            (-10.0, b"\x18\xfc"),
        ],
        ids=["10.0", "-10.0"],
    )
    def test_encode(self, value: float, expected_raw: bytes) -> None:
        assert encode("IS100", value) == expected_raw


class TestIU2Codec:
    """IU2 — unsigned integer ÷ 2 (0.5 precision), little-endian.

    Technique: Boundary Value Analysis.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0.0),
            (b"\x01\x00", 0.5),
            (b"\x64\x00", 50.0),  # 100 / 2
            (b"\xc8\x00", 100.0),  # 200 / 2
        ],
        ids=["zero", "0.5", "50.0", "100.0"],
    )
    def test_decode(self, raw: bytes, expected: float) -> None:
        result = decode("IU2", raw)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected_raw"),
        [
            (0.0, b"\x00\x00"),
            (50.0, b"\x64\x00"),
        ],
        ids=["zero", "50.0"],
    )
    def test_encode(self, value: float, expected_raw: bytes) -> None:
        assert encode("IU2", value) == expected_raw


class TestIU10Codec:
    """IU10 — unsigned integer ÷ 10, little-endian.

    Technique: Boundary Value Analysis.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0.0),
            (b"\xe8\x03", 100.0),  # 1000 / 10
            (b"\x01\x00", 0.1),
        ],
        ids=["zero", "100.0", "0.1"],
    )
    def test_decode(self, raw: bytes, expected: float) -> None:
        result = decode("IU10", raw)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected_raw"),
        [
            (100.0, b"\xe8\x03"),
        ],
        ids=["100.0"],
    )
    def test_encode(self, value: float, expected_raw: bytes) -> None:
        assert encode("IU10", value) == expected_raw


class TestIU3600Codec:
    """IU3600 — unsigned integer ÷ 3600, little-endian.

    Converts raw seconds-ish units to hours.

    Technique: Boundary Value Analysis.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0.0),
            (b"\x10\x0e", 1.0),  # 3600 / 3600
            (b"\x20\x1c", 2.0),  # 7200 / 3600
        ],
        ids=["zero", "1h", "2h"],
    )
    def test_decode(self, raw: bytes, expected: float) -> None:
        result = decode("IU3600", raw)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "expected_raw"),
        [
            (1.0, b"\x10\x0e"),
        ],
        ids=["1h"],
    )
    def test_encode(self, value: float, expected_raw: bytes) -> None:
        assert encode("IU3600", value) == expected_raw


class TestIUNONCodec:
    """IUNON — unsigned integer, no scaling, little-endian.

    Technique: Boundary Value Analysis.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0),
            (b"\x2a\x00", 42),
            (b"\xff\xff", 65535),  # max unsigned 16-bit
        ],
        ids=["zero", "42", "max-u16"],
    )
    def test_decode(self, raw: bytes, expected: int) -> None:
        assert decode("IUNON", raw) == expected

    @pytest.mark.parametrize(
        ("value", "expected_raw"),
        [
            (0, b"\x00\x00"),
            (42, b"\x2a\x00"),
            (65535, b"\xff\xff"),
        ],
        ids=["zero", "42", "max-u16"],
    )
    def test_encode(self, value: int, expected_raw: bytes) -> None:
        assert encode("IUNON", value) == expected_raw

    def test_round_trip(self) -> None:
        raw = b"\x39\x05"
        assert encode("IUNON", decode("IUNON", raw)) == raw


# =============================================================================
# Partial Register Codecs — read-only, extract sub-byte
# =============================================================================


class TestPR2Codec:
    """PR2 — read second byte as unsigned int (read-only).

    From a 2-byte register, only the second byte is the value.

    Technique: Specification-based Testing.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0),
            (b"\xff\x2a", 42),  # First byte ignored
            (b"\x00\xff", 255),
        ],
        ids=["zero", "42-ignores-first", "max-byte"],
    )
    def test_decode(self, raw: bytes, expected: int) -> None:
        assert decode("PR2", raw) == expected

    def test_encode_raises(self) -> None:
        """PR2 is read-only — encoding raises CodecError.

        Technique: Error Guessing — read-only codec rejects writes.
        """
        with pytest.raises(CodecError, match="[Rr]ead.only"):
            encode("PR2", 42)


class TestPR3Codec:
    """PR3 — read first byte as unsigned int ÷ 2 (read-only).

    Technique: Specification-based Testing.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x00\x00", 0.0),
            (b"\x64\xff", 50.0),  # 100 / 2; second byte ignored
            (b"\x01\x00", 0.5),  # 1 / 2
        ],
        ids=["zero", "50.0-ignores-second", "0.5"],
    )
    def test_decode(self, raw: bytes, expected: float) -> None:
        result = decode("PR3", raw)
        assert result == pytest.approx(expected)

    def test_encode_raises(self) -> None:
        """PR3 is read-only — encoding raises CodecError."""
        with pytest.raises(CodecError, match="[Rr]ead.only"):
            encode("PR3", 50.0)


# =============================================================================
# Device Type Codec
# =============================================================================


class TestDeviceTypeCodec:
    """DT — 2-byte big-endian device type code to description string.

    Technique: Decision Table (representative subset).
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (b"\x20\x98", "V200KW2, Protokoll: KW2"),
            (b"\x20\x4d", "V200WO1C, Protokoll: P300"),
            (b"\x00\x00", "unknown"),
        ],
        ids=["v200kw2", "v200wo1c", "unknown-zero"],
    )
    def test_decode(self, raw: bytes, expected: str) -> None:
        assert decode("DT", raw) == expected

    def test_encode_known_device(self) -> None:
        """Encode a known device name back to its 2-byte code."""
        result = encode("DT", "V200KW2, Protokoll: KW2")
        assert result == b"\x20\x98"

    def test_decode_unknown_code_raises(self) -> None:
        """Technique: Error Guessing — unregistered device code."""
        with pytest.raises(CodecError):
            decode("DT", b"\xff\xff")


# =============================================================================
# Error Set Codec (read-only)
# =============================================================================


class TestErrorSetCodec:
    """ES — 9-byte error history record: error code + BCD timestamp.

    Byte layout: [error_code, YY_hi, YY_lo, MM, DD, ??, HH, MM, SS]
    where timestamp bytes are BCD-encoded (hex digits represent decimals).

    Technique: Specification-based Testing + Error Guessing.
    """

    def test_decode_no_error(self) -> None:
        """Error code 0x00 = normal operation, with a sample timestamp.

        Timestamp BCD: 0x20 0x24 0x06 0x15 0x00 0x14 0x30 0x00
        → year=2024, month=06, day=15, hour=14, minute=30, second=00
        """
        raw = b"\x00\x20\x24\x06\x15\x00\x14\x30\x00"
        error_str, timestamp = decode("ES", raw)
        assert error_str == "Regelbetrieb (kein Fehler)"
        assert timestamp == datetime(2024, 6, 15, 14, 30, 0)

    def test_decode_burner_fault(self) -> None:
        """Error code 0xD1 = Brennerstoerung (burner fault).

        Timestamp: 2023-12-01 08:15:30
        BCD: 0x20 0x23 0x12 0x01 0x00 0x08 0x15 0x30
        """
        raw = b"\xd1\x20\x23\x12\x01\x00\x08\x15\x30"
        error_str, timestamp = decode("ES", raw)
        assert error_str == "Brennerstoerung"
        assert timestamp == datetime(2023, 12, 1, 8, 15, 30)

    def test_decode_flame_signal_missing(self) -> None:
        """Error code 0xF4 = flame signal not present."""
        raw = b"\xf4\x20\x24\x01\x10\x00\x12\x00\x00"
        error_str, _ = decode("ES", raw)
        assert error_str == "Flammensigal nicht vorhanden"

    def test_decode_unknown_error_code_raises(self) -> None:
        """Unknown error codes should raise CodecError.

        Technique: Error Guessing — byte value not in error table.
        """
        raw = b"\x07\x20\x24\x01\x01\x00\x00\x00\x00"  # 0x07 not in table
        with pytest.raises(CodecError):
            decode("ES", raw)

    def test_encode_raises_read_only(self) -> None:
        """ES is read-only — errors are reported by the boiler, not written.

        Technique: Error Guessing — read-only codec.
        """
        with pytest.raises(CodecError, match="[Rr]ead.only"):
            encode("ES", ("some error", datetime.now()))


# =============================================================================
# System Time Codec (read-only)
# =============================================================================


class TestSystemTimeCodec:
    """TI — 8-byte BCD system time → datetime.

    Byte layout: [YY_hi, YY_lo, MM, DD, ??, HH, MM, SS]
    BCD-encoded: each byte's hex representation is the decimal value.

    Technique: Specification-based Testing.
    """

    def test_decode_basic(self) -> None:
        """Standard timestamp: 2024-06-15 14:30:00."""
        raw = b"\x20\x24\x06\x15\x00\x14\x30\x00"
        result = decode("TI", raw)
        assert result == datetime(2024, 6, 15, 14, 30, 0)

    def test_decode_midnight(self) -> None:
        """Midnight on New Year's: 2025-01-01 00:00:00."""
        raw = b"\x20\x25\x01\x01\x00\x00\x00\x00"
        result = decode("TI", raw)
        assert result == datetime(2025, 1, 1, 0, 0, 0)

    def test_decode_end_of_day(self) -> None:
        """Last second of the day: 2023-12-31 23:59:59."""
        raw = b"\x20\x23\x12\x31\x00\x23\x59\x59"
        result = decode("TI", raw)
        assert result == datetime(2023, 12, 31, 23, 59, 59)

    def test_encode_raises_read_only(self) -> None:
        """TI is read-only (system time is set internally).

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="[Rr]ead.only"):
            encode("TI", datetime.now())


# =============================================================================
# Cycle Time Codec
# =============================================================================


class TestCycleTimeCodec:
    """CT — 8-byte cycle time with 4 start/stop time slot pairs.

    Each time slot is 1 byte packed as: (hours << 3) | (minutes // 10).
    Special sentinel: hours=31, minutes=70 → None (unused slot).

    Technique: Specification-based Testing + Boundary Value Analysis.
    """

    def test_decode_single_active_slot(self) -> None:
        """One active slot (06:00–22:00), rest unused.

        Slot 1: start=06:00 → (6<<3)|(0//10) = 48 = 0x30
                 stop =22:00 → (22<<3)|(0//10) = 176 = 0xB0
        Slots 2-4: unused → (31<<3)|(70//10) = 255 = 0xFF
        """
        raw = b"\x30\xb0\xff\xff\xff\xff\xff\xff"
        result = decode("CT", raw)
        assert len(result) == 4
        # Active slot
        assert result[0] == CycleTimeSlot(
            start_hour=6, start_minute=0, stop_hour=22, stop_minute=0
        )
        # Unused slots have None fields
        assert result[1].start_hour is None
        assert result[1].start_minute is None
        assert result[1].stop_hour is None
        assert result[1].stop_minute is None

    def test_decode_slot_with_minutes(self) -> None:
        """Slot at 07:30–18:20.

        start: (7<<3)|(30//10) = 56+3 = 59 = 0x3B
        stop:  (18<<3)|(20//10) = 144+2 = 146 = 0x92
        """
        raw = b"\x3b\x92\xff\xff\xff\xff\xff\xff"
        result = decode("CT", raw)
        assert result[0] == CycleTimeSlot(
            start_hour=7, start_minute=30, stop_hour=18, stop_minute=20
        )

    def test_decode_all_unused(self) -> None:
        """All four slots unused → all None."""
        raw = b"\xff" * 8
        result = decode("CT", raw)
        for slot in result:
            assert slot.start_hour is None

    def test_encode_single_active_slot(self) -> None:
        """Encode one active slot + 3 unused."""
        unused = CycleTimeSlot(
            start_hour=None,
            start_minute=None,
            stop_hour=None,
            stop_minute=None,
        )
        slots = [
            CycleTimeSlot(
                start_hour=6,
                start_minute=0,
                stop_hour=22,
                stop_minute=0,
            ),
            unused,
            unused,
            unused,
        ]
        result = encode("CT", slots)
        assert result == b"\x30\xb0\xff\xff\xff\xff\xff\xff"

    def test_round_trip(self) -> None:
        """Technique: Round-trip Testing."""
        raw = b"\x3b\x92\xff\xff\xff\xff\xff\xff"
        assert encode("CT", decode("CT", raw)) == raw


# =============================================================================
# Codec Error Handling
# =============================================================================


class TestCodecErrorHandling:
    """Cross-cutting error scenarios.

    Technique: Error Guessing — boundary and structural failures.
    """

    def test_decode_empty_bytes_for_numeric_raises(self) -> None:
        """Empty bytes should raise for a fixed-length codec."""
        with pytest.raises((CodecError, ValueError)):
            decode("IUNON", b"")

    def test_encode_unknown_type_code_raises(self) -> None:
        """Encoding with an unknown type code raises CodecError."""
        with pytest.raises(CodecError):
            encode("NOPE", 42)

    def test_decode_unknown_type_code_raises(self) -> None:
        """Decoding with an unknown type code raises CodecError."""
        with pytest.raises(CodecError):
            decode("NOPE", b"\x00")
