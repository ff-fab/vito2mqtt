"""Data type encoder/decoder for Vitodens 200-W parameters.

Supports 11 type codes actually used by the Vitodens 200-W:

Numeric (language-neutral):
    IS10    — signed fixed-point ÷10
    IUNON   — unsigned integer (no scaling)
    IU3600  — unsigned integer ÷3600 (seconds → hours)
    PR2     — second byte, unsigned
    PR3     — first byte, unsigned ÷2

Enum (language-configurable per ADR-006):
    BA      — Betriebsart (operating mode)
    USV     — Umschaltventil (switch valve)
    ES      — Fehlerspeicher (error history)

Structural (language-neutral):
    RT      — ReturnStatus (IntEnum)
    CT      — CycleTime (timer schedule)
    TI      — SystemTime (BCD-packed datetime)

References:
    ADR-004 — Optolink Protocol Design
    ADR-006 — Configurable Signal Language (DE/EN)
"""
