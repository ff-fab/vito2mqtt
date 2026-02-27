"""Optolink P300 protocol implementation for Viessmann boilers.

Internal sub-package implementing the P300 serial protocol used by the Viessmann
Optolink interface. Structured in four layers:

- ``telegram`` — P300 telegram framing (encode/decode/checksum)
- ``codec`` — Data type encoder/decoder (IS10, IUNON, BA, CT, etc.)
- ``commands`` — Vitodens 200-W command registry (address → signal mapping)
- ``transport`` — Session controller (init handshake, read/write orchestration)

See ADR-004 for architectural rationale.
"""
