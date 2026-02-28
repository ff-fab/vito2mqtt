"""P300 telegram framing: encode, decode, and checksum computation.

The P300 protocol uses a binary telegram format::

    0x41 | len | type | mode | addr_hi | addr_lo | data_len | [payload] | csum

Where checksum is the sum of bytes from type through payload, mod 256.

References:
    ADR-004 — Optolink Protocol Design
"""
