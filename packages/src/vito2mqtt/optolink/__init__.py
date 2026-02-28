"""Optolink P300 protocol implementation for Vitodens 200-W.

This sub-package implements the P300 serial protocol used by the Viessmann
Optolink interface. It is structured as four layers per ADR-004:

- ``telegram`` — P300 telegram framing (encode/decode/checksum)
- ``codec`` — Data type encoder/decoder (11 types for Vitodens 200-W)
- ``commands`` — Command registry mapping addresses → signal names
- ``transport`` — Session controller (handshake + read/write orchestration)
"""
