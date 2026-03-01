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

"""Shared fixtures for optolink unit tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

import pytest

from vito2mqtt.optolink.telegram import P300Mode, P300Type, checksum

# ---------------------------------------------------------------------------
# Fake serial port
# ---------------------------------------------------------------------------


class FakeSerial:
    """Programmable fake serial port for transport tests.

    Queue response bytes via the constructor or :meth:`push`, then let
    the code-under-test call :meth:`read` / :meth:`write` as normal.
    All bytes written by the CUT are captured in :attr:`written`.
    """

    def __init__(self, responses: Sequence[bytes] = ()) -> None:
        self._responses: deque[bytes] = deque(responses)
        self.written: list[bytes] = []
        self._closed: bool = False

    def push(self, *data: bytes) -> None:
        """Queue additional response bytes."""
        self._responses.extend(data)

    async def read(self, n: int) -> bytes:
        if not self._responses:
            return b""  # Simulate timeout
        chunk = self._responses.popleft()
        return chunk[:n]

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    async def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed


@pytest.fixture
def fake_serial() -> FakeSerial:
    """Return a fresh :class:`FakeSerial` with no pre-loaded responses."""
    return FakeSerial()


# ---------------------------------------------------------------------------
# Telegram builder helpers
# ---------------------------------------------------------------------------


def build_response(
    address: int,
    payload: bytes,
    *,
    error: bool = False,
    mode: P300Mode = P300Mode.READ,
) -> bytes:
    """Build a raw P300 response telegram for testing.

    Constructs a valid telegram (start byte, body, checksum) that
    :func:`telegram.decode_telegram` will successfully decode.

    Args:
        address: 2-byte memory address.
        payload: Response payload bytes.
        error: If ``True``, sets the telegram type to ``P300Type.ERROR``.
        mode: Telegram mode (defaults to READ).

    Returns:
        Complete raw telegram bytes.
    """
    ttype = P300Type.ERROR if error else P300Type.RESPONSE
    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF
    data_len = len(payload)
    body_content = bytes([ttype, mode, addr_hi, addr_lo, data_len]) + payload
    frame_len = len(body_content)
    # body = everything between start byte and checksum
    body = bytes([frame_len]) + body_content
    raw = bytes([0x41]) + body
    return raw + bytes([checksum(body)])
