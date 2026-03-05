# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Pure-logic functions for the legionella treatment feature.

The state machine and device registration will be added in Phase 2.

This module provides:
- ``TIMER_SIGNAL_FOR_DAY``: Maps ``datetime.weekday()`` values to the
  corresponding hot-water timer signal names in the command registry.
- ``is_within_heating_window``: Checks whether a given time falls within
  an active heating schedule slot with sufficient remaining margin.

References:
    ADR-007 — Telemetry Coalescing Groups
"""

from __future__ import annotations

from datetime import time, timedelta

from vito2mqtt.optolink.codec import CycleTimeSchedule

# ---------------------------------------------------------------------------
# Day-to-signal mapping
# ---------------------------------------------------------------------------

TIMER_SIGNAL_FOR_DAY: dict[int, str] = {
    0: "timer_hw_monday",
    1: "timer_hw_tuesday",
    2: "timer_hw_wednesday",
    3: "timer_hw_thursday",
    4: "timer_hw_friday",
    5: "timer_hw_saturday",
    6: "timer_hw_sunday",
}
"""Maps ``datetime.weekday()`` (0=Monday … 6=Sunday) to signal names."""

# ---------------------------------------------------------------------------
# Heating window check
# ---------------------------------------------------------------------------


def is_within_heating_window(
    schedule: CycleTimeSchedule,
    now: time,
    safety_margin_minutes: int = 30,
) -> bool:
    """Check whether *now* falls within any active time slot in *schedule*.

    A slot matches when ``start <= now`` **and** the remaining time before
    the slot ends is **strictly greater** than *safety_margin_minutes*.

    .. note:: Overnight windows (``end < start``) are not supported and
       will never match.  Boiler timer programs do not span midnight.

    Parameters:
        schedule: Decoded cycle-time schedule — a list of up to 4
            ``[[start_h, start_m], [end_h, end_m]]`` pairs.  Slots whose
            hours/minutes contain ``None`` are treated as inactive.
        now: Current time of day to test.
        safety_margin_minutes: Minimum number of full minutes that must
            remain before the slot ends for the check to pass.  Must be
            non-negative.

    Returns:
        ``True`` if any active slot satisfies the condition, ``False``
        otherwise.

    Raises:
        ValueError: If *safety_margin_minutes* is negative.
    """
    if safety_margin_minutes < 0:
        msg = f"safety_margin_minutes must be non-negative, got {safety_margin_minutes}"
        raise ValueError(msg)
    for pair in schedule:
        start_slot, end_slot = pair

        # Skip inactive ("not set") slots
        if None in start_slot or None in end_slot:
            continue

        # At this point all values are confirmed int — narrow for mypy
        start_h: int = start_slot[0]  # type: ignore[assignment]
        start_m: int = start_slot[1]  # type: ignore[assignment]
        end_h: int = end_slot[0]  # type: ignore[assignment]
        end_m: int = end_slot[1]  # type: ignore[assignment]

        slot_start = time(start_h, start_m)

        # Compute the effective end by subtracting the safety margin.
        # We use timedelta arithmetic through a datetime anchor to avoid
        # negative-time edge cases.
        _anchor = timedelta(hours=end_h, minutes=end_m)
        _margin = timedelta(minutes=safety_margin_minutes)
        effective_end_td = _anchor - _margin

        # If the margin exceeds the end time the effective end wraps
        # negative — no useful window remains.
        if effective_end_td.total_seconds() < 0:
            continue

        total_seconds = int(effective_end_td.total_seconds())
        effective_end = time(total_seconds // 3600, (total_seconds % 3600) // 60)

        if slot_start <= now < effective_end:
            return True

    return False
