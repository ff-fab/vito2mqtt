"""P300 session controller: handshake and read/write orchestration.

Handles the P300 initialization sequence (0x04 → 0x05 exchange) and
orchestrates read/write requests over the serial link. Checks RT
(ReturnStatus) responses and raises DeviceError on error conditions.

References:
    ADR-004 — Optolink Protocol Design
"""
