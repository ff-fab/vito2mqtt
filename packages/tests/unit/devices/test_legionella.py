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

"""Unit tests for devices/legionella.py — Heating window check (pure logic).

Test Techniques Used:
- Specification-based: Verify is_within_heating_window contract
- Boundary Value Analysis: Exact margin boundary, one-minute-before boundary
- Equivalence Partitioning: Inside/outside window, empty/None schedules
- Cross-reference: TIMER_SIGNAL_FOR_DAY values exist in COMMANDS registry
"""

from __future__ import annotations

from datetime import time

import pytest

from vito2mqtt.devices.legionella import TIMER_SIGNAL_FOR_DAY, is_within_heating_window
from vito2mqtt.optolink.codec import CycleTimeSchedule
from vito2mqtt.optolink.commands import COMMANDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Standard single-window schedule: 06:00–14:00
_WINDOW_06_14: CycleTimeSchedule = [
    [[6, 0], [14, 0]],
    [[None, None], [None, None]],
    [[None, None], [None, None]],
    [[None, None], [None, None]],
]


def _schedule_with_two_windows() -> CycleTimeSchedule:
    """Two active windows: 06:00–10:00 and 16:00–22:00."""
    return [
        [[6, 0], [10, 0]],
        [[16, 0], [22, 0]],
        [[None, None], [None, None]],
        [[None, None], [None, None]],
    ]


# ===========================================================================
# is_within_heating_window
# ===========================================================================


class TestIsWithinHeatingWindow:
    """Tests for the is_within_heating_window pure function.

    Technique: Specification-based — verify the matching logic against the
    documented contract (start <= now < effective_end).
    """

    def test_within_active_window(self) -> None:
        """now=10:00, window 06:00–14:00, margin=30 → True.

        Technique: Equivalence Partitioning — clearly inside the window.
        """
        # Arrange
        now = time(10, 0)

        # Act
        result = is_within_heating_window(_WINDOW_06_14, now, safety_margin_minutes=30)

        # Assert
        assert result is True

    def test_outside_all_windows(self) -> None:
        """now=03:00, window 06:00–14:00, margin=30 → False.

        Technique: Equivalence Partitioning — before the window starts.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(3, 0), safety_margin_minutes=30
        )

        assert result is False

    def test_near_end_within_margin(self) -> None:
        """now=13:35, window 06:00–14:00, margin=30 → False (only 25 min left).

        Technique: Boundary Value Analysis — inside the window but too close
        to the end for the safety margin.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 35), safety_margin_minutes=30
        )

        assert result is False

    def test_exactly_at_margin_boundary(self) -> None:
        """now=13:30, window 06:00–14:00, margin=30 → False.

        Technique: Boundary Value Analysis — effective_end is 13:30,
        condition is now < effective_end so exactly-at is excluded.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 30), safety_margin_minutes=30
        )

        assert result is False

    def test_one_minute_before_margin(self) -> None:
        """now=13:29, window 06:00–14:00, margin=30 → True (31 min left).

        Technique: Boundary Value Analysis — one minute inside the valid zone.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 29), safety_margin_minutes=30
        )

        assert result is True

    def test_before_window_start(self) -> None:
        """now=05:59, window 06:00–14:00, margin=30 → False.

        Technique: Boundary Value Analysis — one minute before the start.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(5, 59), safety_margin_minutes=30
        )

        assert result is False

    def test_exactly_at_window_start(self) -> None:
        """now=06:00, window 06:00–14:00, margin=30 → True.

        Technique: Boundary Value Analysis — start is inclusive.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(6, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_empty_schedule(self) -> None:
        """Empty schedule → False.

        Technique: Equivalence Partitioning — degenerate input.
        """
        result = is_within_heating_window([], time(10, 0), safety_margin_minutes=30)

        assert result is False

    def test_all_slots_none(self) -> None:
        """All slots have None values → False.

        Technique: Equivalence Partitioning — all-inactive schedule.
        """
        schedule: CycleTimeSchedule = [
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=30
        )

        assert result is False

    def test_second_slot_matches(self) -> None:
        """First slot doesn't match, second does → True.

        Technique: Specification-based — any matching slot returns True.
        """
        schedule = _schedule_with_two_windows()

        # 18:00 is within the second window (16:00–22:00)
        result = is_within_heating_window(
            schedule, time(18, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_multiple_windows_first_matches(self) -> None:
        """Two valid windows, now in first → True.

        Technique: Specification-based — early match short-circuits.
        """
        schedule = _schedule_with_two_windows()

        # 08:00 is within the first window (06:00–10:00)
        result = is_within_heating_window(
            schedule, time(8, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_mixed_none_and_valid_slots(self) -> None:
        """Some None slots, one valid matching slot → True.

        Technique: Equivalence Partitioning — interleaved active/inactive.
        """
        schedule: CycleTimeSchedule = [
            [[None, None], [None, None]],
            [[8, 0], [16, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_zero_safety_margin(self) -> None:
        """margin=0, now=13:59, window 06:00–14:00 → True.

        Technique: Boundary Value Analysis — zero margin means the full
        window is usable up to (but not including) the end.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 59), safety_margin_minutes=0
        )

        assert result is True

    def test_partially_none_slot_is_skipped(self) -> None:
        """A slot with only hours=None (e.g. [None, 0]) is inactive.

        Technique: Error Guessing — hardware byte 0xF8 decodes as
        [None, 0]; the ``None in slot`` guard must catch partial None.
        """
        schedule: CycleTimeSchedule = [
            [[None, 0], [14, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=30
        )

        assert result is False

    def test_zero_duration_window(self) -> None:
        """Window with start == end is never matchable.

        Technique: Boundary Value Analysis — zero-duration window means
        start <= now < effective_end can never be satisfied.
        """
        schedule: CycleTimeSchedule = [
            [[10, 0], [10, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=0
        )

        assert result is False

    def test_margin_exceeds_window_duration(self) -> None:
        """Window 06:00–06:20, margin=30 → never matchable.

        Technique: Boundary Value Analysis — effective_end becomes negative
        (before start), so the window is skipped.
        """
        schedule: CycleTimeSchedule = [
            [[6, 0], [6, 20]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(6, 10), safety_margin_minutes=30
        )

        assert result is False

    def test_negative_margin_raises(self) -> None:
        """Negative safety margin is a caller bug.

        Technique: Error Guessing — guard against invalid input.
        """
        with pytest.raises(ValueError, match="non-negative"):
            is_within_heating_window(
                _WINDOW_06_14, time(10, 0), safety_margin_minutes=-1
            )


# ===========================================================================
# TIMER_SIGNAL_FOR_DAY
# ===========================================================================


class TestTimerSignalForDay:
    """Tests for the TIMER_SIGNAL_FOR_DAY constant.

    Technique: Cross-reference — mapping must align with the command registry.
    """

    def test_covers_all_seven_days(self) -> None:
        """Dict has exactly 7 entries, keys 0–6.

        Technique: Specification-based — one entry per weekday.
        """
        assert set(TIMER_SIGNAL_FOR_DAY.keys()) == {0, 1, 2, 3, 4, 5, 6}
        assert len(TIMER_SIGNAL_FOR_DAY) == 7

    def test_monday_maps_correctly(self) -> None:
        """0 → 'timer_hw_monday'.

        Technique: Specification-based — spot check.
        """
        assert TIMER_SIGNAL_FOR_DAY[0] == "timer_hw_monday"

    def test_sunday_maps_correctly(self) -> None:
        """6 → 'timer_hw_sunday'.

        Technique: Specification-based — spot check.
        """
        assert TIMER_SIGNAL_FOR_DAY[6] == "timer_hw_sunday"

    @pytest.mark.parametrize("day", range(7), ids=lambda d: f"day_{d}")
    def test_signal_names_match_commands(self, day: int) -> None:
        """All values exist in the COMMANDS registry.

        Technique: Cross-reference — every signal name is a valid command.
        """
        signal_name = TIMER_SIGNAL_FOR_DAY[day]

        assert signal_name in COMMANDS, f"{signal_name!r} not found in COMMANDS"
