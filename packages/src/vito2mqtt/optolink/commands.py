"""Vitodens 200-W command registry.

Maps P300 memory addresses to signal names, data types, access modes,
and byte lengths. Covers ~50 commands across four polling groups:

- READ_5MIN   — temperatures, pump statuses, switch valve, error register
- READ_1HR    — burner stats, operating modes
- READ_4HRS   — frost warnings
- ON_DEMAND   — set points, timers, characteristics, additional error registers

References:
    ADR-004 — Optolink Protocol Design
"""
