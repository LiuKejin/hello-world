"""
Gantry service (orchestrator)
=============================

The application's use-case layer. It owns the long-lived collaborators
(controller, telemetry, current configuration) and exposes the handful of
operations the transport layer needs: ``get_status``, ``set_config``, ``home``,
``start_sequence`` and ``stop``.

Concurrency model
-----------------
A pick-and-place cycle is a long, blocking operation, so it runs on a single
background worker thread. The API thread only ever reads the thread-safe
telemetry snapshot, never the robot directly. ``stop`` sets an abort
:class:`threading.Event` that the in-flight motion polls cooperatively.

The ``vention-state-machine`` dependency is imported lazily: the rest of the
backend (status, configuration, telemetry) stays fully functional even when the
library is unavailable, and ``start_sequence`` returns a clear error instead of
crashing the process.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .domain import ConfigError, GantryConfig, Phase, validate_config
from .robot_controller import RobotController, RobotError
from .telemetry import TelemetryHub


@dataclass
class CommandResult:
    success: bool
    message: str

    def to_dict(self) -> dict:
        return {"success": self.success, "message": self.message}


class GantryService:
    def __init__(
        self,
        controller: RobotController,
        telemetry: TelemetryHub,
        config: GantryConfig | None = None,
        home_speed: float = 50.0,
    ) -> None:
        self._controller = controller
        self._telemetry = telemetry
        self._config = validate_config(config or GantryConfig())
        self._home_speed = home_speed

        self._lock = threading.Lock()
        self._abort = threading.Event()
        self._worker: threading.Thread | None = None

        self._sm_available, self._sm_reason = _probe_state_machine()

    # -- Queries ---------------------------------------------------------
    @property
    def config(self) -> GantryConfig:
        return self._config

    def is_busy(self) -> bool:
        with self._lock:
            return self._busy_locked()

    def get_status(self) -> dict:
        snapshot = self._telemetry.get()
        return {
            **snapshot.to_dict(),
            "busy": self.is_busy(),
            "config": _config_to_dict(self._config),
            "state_machine_available": self._sm_available,
        }

    # -- Configuration ---------------------------------------------------
    def set_config(self, **changes) -> CommandResult:
        with self._lock:
            if self._busy_locked():
                return CommandResult(False, "Cannot change configuration while busy")
            try:
                self._config = self._config.replace(**changes)
            except (ConfigError, TypeError) as exc:
                return CommandResult(False, str(exc))
        return CommandResult(True, "Configuration updated")

    # -- Commands --------------------------------------------------------
    def home(self) -> CommandResult:
        with self._lock:
            if self._busy_locked():
                return CommandResult(False, "Robot is busy")
            self._abort.clear()
            self._spawn_locked(self._run_home)
        return CommandResult(True, "Homing started")

    def start_sequence(self) -> CommandResult:
        with self._lock:
            if self._busy_locked():
                return CommandResult(False, "Robot is busy")
            if not self._sm_available:
                return CommandResult(False, self._sm_reason)
            self._abort.clear()
            config = self._config  # snapshot for this run
            self._spawn_locked(lambda: self._run_sequence(config))
        return CommandResult(True, "Pick-and-place sequence started")

    def stop(self) -> CommandResult:
        self._abort.set()
        return CommandResult(True, "Stop requested")

    # -- Worker bodies ---------------------------------------------------
    def _run_home(self) -> None:
        self._telemetry.set_phase(Phase.HOMING.value)
        try:
            self._controller.home(self._home_speed, should_abort=self._abort.is_set)
            self._telemetry.set_phase(Phase.IDLE.value)
        except RobotError as exc:
            if self._abort.is_set():
                self._telemetry.set_phase(Phase.IDLE.value)
            else:
                self._telemetry.set_phase(Phase.FAULT.value, error=str(exc))

    def _run_sequence(self, config: GantryConfig) -> None:
        # Imported here so the module only loads when actually needed.
        from .state_machine import PickPlaceStateMachine

        machine = PickPlaceStateMachine(
            controller=self._controller,
            config=config,
            telemetry=self._telemetry,
            should_abort=self._abort.is_set,
        )
        # trigger("start") synchronously walks the whole cycle; phase faults are
        # handled inside the machine, so nothing should escape here.
        machine.trigger("start")

    # -- Internals -------------------------------------------------------
    def _busy_locked(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _spawn_locked(self, target) -> None:
        self._worker = threading.Thread(target=target, daemon=True)
        self._worker.start()


def _config_to_dict(config: GantryConfig) -> dict:
    return {
        "cube_position": list(config.cube_position),
        "destination": list(config.destination),
        "home_position": list(config.home_position),
        "safe_z": config.safe_z,
        "speed": config.speed,
    }


def _probe_state_machine() -> tuple[bool, str]:
    """Check whether the orchestration library can be imported."""
    try:
        import state_machine.core  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return (
            False,
            "vention-state-machine is not available "
            f"(requires Python 3.10): {exc}",
        )
    return True, "ok"
