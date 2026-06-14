"""
Telemetry hub
=============

A small, thread-safe store of the latest :class:`GantrySnapshot`.

The motion sequence runs on a background worker thread while FastAPI serves
requests on the event loop, so the cell's live state is shared state. The hub
guards it with a lock and offers a publish/subscribe hook used by the
vention-communication telemetry stream (see ``app/comm.py``).

The hub is intentionally transport-agnostic: it knows nothing about REST,
WebSockets or RPC. Producers call :meth:`set_motion` / :meth:`set_phase`;
consumers call :meth:`get` or :meth:`subscribe`.
"""

from __future__ import annotations

import threading
from typing import Callable, List

from .domain import GantrySnapshot, Phase, Vector3

Subscriber = Callable[[GantrySnapshot], None]


class TelemetryHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = GantrySnapshot(
            position=[0.0, 0.0, 0.0],
            gripper="OPEN",
            moving=False,
            phase=Phase.IDLE.value,
            error=None,
        )
        self._subscribers: List[Subscriber] = []

    def get(self) -> GantrySnapshot:
        """Return a copy of the current snapshot (safe to serialise)."""
        with self._lock:
            return GantrySnapshot(
                position=list(self._snapshot.position),
                gripper=self._snapshot.gripper,
                moving=self._snapshot.moving,
                phase=self._snapshot.phase,
                error=self._snapshot.error,
            )

    def set_motion(self, position: Vector3, gripper: str, moving: bool) -> None:
        """Update kinematic state. Wired to ``RobotController.on_update``."""
        with self._lock:
            self._snapshot.position = list(position)
            self._snapshot.gripper = gripper
            self._snapshot.moving = moving
            snapshot = self._copy_locked()
        self._notify(snapshot)

    def set_phase(self, phase: str, error: str | None = None) -> None:
        """Update the lifecycle phase (and optional fault message)."""
        with self._lock:
            self._snapshot.phase = phase
            self._snapshot.error = error
            snapshot = self._copy_locked()
        self._notify(snapshot)

    def subscribe(self, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(callback)

    # -- Internals -------------------------------------------------------
    def _copy_locked(self) -> GantrySnapshot:
        return GantrySnapshot(
            position=list(self._snapshot.position),
            gripper=self._snapshot.gripper,
            moving=self._snapshot.moving,
            phase=self._snapshot.phase,
            error=self._snapshot.error,
        )

    def _notify(self, snapshot: GantrySnapshot) -> None:
        for callback in list(self._subscribers):
            try:
                callback(snapshot)
            except Exception:  # noqa: BLE001 - a bad subscriber must not break motion
                pass
