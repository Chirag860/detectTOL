"""App lifecycle: shut down after the last tab closed; do not start twice."""

from __future__ import annotations

import asyncio
import contextlib
import socket
from types import SimpleNamespace

import pytest

pytest.importorskip("nicegui", reason="nicegui is not installed")
pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.app import ui as app_ui


def _run_watch(monkeypatch: pytest.MonkeyPatch, timeline: list[bool]) -> int | None:
    """Drive _watch_clients with fake clients; ``timeline`` = connected? at each 5 s tick.

    Returns the tick at which the app was shut down, or None."""
    tick = {"n": -1}
    shutdown_at: dict[str, int | None] = {"tick": None}
    clock = {"t": 0.0}
    fake_client = SimpleNamespace(instances={})

    async def fake_sleep(_s: float) -> None:
        tick["n"] += 1
        clock["t"] += 5.0
        if tick["n"] >= len(timeline):
            raise asyncio.CancelledError
        fake_client.instances = {"c": SimpleNamespace(has_socket_connection=timeline[tick["n"]])}

    monkeypatch.setattr(app_ui.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(app_ui.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(app_ui, "Client", fake_client)
    monkeypatch.setattr(app_ui.app, "shutdown", lambda: shutdown_at.__setitem__("tick", tick["n"]))
    monkeypatch.setattr(app_ui, "IDLE_SHUTDOWN_S", 15.0)
    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(app_ui._watch_clients())
    return shutdown_at["tick"]


def test_waits_for_a_first_tab_then_shuts_down_after_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ticks 5 s apart, idle limit 15 s: no tab yet (never stops), tab open, then closed at
    tick 3; idle measured from tick 3 -> 15 s reached at tick 6."""
    timeline = [False, False, True, False, False, False, False, False]
    assert _run_watch(monkeypatch, timeline) == 6


def test_a_reconnecting_tab_resets_the_idle_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    timeline = [True, False, False, True, False, False, False, False]
    assert _run_watch(monkeypatch, timeline) == 7


def test_port_in_use_detection() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert app_ui._port_in_use("127.0.0.1", port)
    assert not app_ui._port_in_use("127.0.0.1", port)
