"""
Robot controller (hardware adapter)
===================================

Thin, framework-free wrapper around the provided ``robot_sim.Robot``.

Its single responsibility is to turn the simulator's *non-blocking* primitives
into *intent-level, blocking* operations the orchestration layer can compose:
``move_to_blocking``, ``home``, ``grip`` and ``release``.

The most important detail (called out in the exercise README) lives here: the
simulator's ``move_to`` advances the robot a little on every call and must be
polled repeatedly until the motion completes. That loop is encapsulated once,
in :meth:`move_to_blocking`, so no higher layer ever has to know about it.

This module is deliberately free of FastAPI and the vention libraries so it can
be unit-tested on any Python version, directly against ``robot_sim``.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from robot_sim import GripperState, Robot

from .domain import SPEED_MAX, SPEED_MIN, Vector3

# Called on every state change with (position, gripper_name, moving).
UpdateCallback = Callable[[Vector3, str, bool], None]
# Cooperative cancellation hook; return True to abort an in-flight motion.
AbortCheck = Callable[[], bool]


class RobotError(RuntimeError):
    """Raised when the simulator rejects a command or a motion is aborted."""


class RobotController:
    """Blocking, intent-level facade over ``robot_sim.Robot``."""

    #: How often to poll ``move_to`` while a motion is in progress (seconds).
    POLL_INTERVAL_S = 0.02
    #: Position tolerance in mm when deciding a target has been reached.
    REACH_TOLERANCE_MM = 1e-6

    def __init__(
        self,
        robot: Optional[Robot] = None,
        on_update: Optional[UpdateCallback] = None,
        poll_interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._robot = robot or Robot()
        self._on_update = on_update
        self._poll_interval_s = poll_interval_s
        self._moving = False

    # -- Telemetry-facing accessors --------------------------------------
    @property
    def position(self) -> Vector3:
        return list(self._robot.current_position)

    @property
    def gripper(self) -> str:
        return self._robot.gripper_state.name

    @property
    def moving(self) -> bool:
        return self._moving

    # -- Commands --------------------------------------------------------
    def move_to_blocking(
        self,
        target: Vector3,
        speed: float,
        should_abort: Optional[AbortCheck] = None,
    ) -> Vector3:
        """Drive the robot to ``target`` and return only once it has arrived.

        Repeatedly calls ``robot_sim.move_to`` (which only advances the robot a
        single time-slice per call) until the simulator reports the axes have
        stopped at the target.

        Raises:
            RobotError: if the simulator rejects the command (out-of-range
                speed/target) or if ``should_abort`` requests cancellation.
        """
        if not SPEED_MIN < speed <= SPEED_MAX:
            raise RobotError(
                f"speed {speed} must be within ({SPEED_MIN}, {SPEED_MAX}] mm/s"
            )

        target = [float(v) for v in target]
        while True:
            if should_abort is not None and should_abort():
                self._set_moving(False)
                raise RobotError("Motion aborted")

            position, axis_speed, error = self._robot.move_to(target, int(speed))
            if error is not None:
                self._set_moving(False)
                raise RobotError(error)

            still_moving = any(v != 0 for v in axis_speed)
            self._set_moving(still_moving)

            if not still_moving and self._reached(position, target):
                break
            time.sleep(self._poll_interval_s)

        self._set_moving(False)
        return self.position

    def home(
        self,
        speed: float = 50.0,
        should_abort: Optional[AbortCheck] = None,
    ) -> Vector3:
        """Move to the robot's configured home position (blocking)."""
        return self.move_to_blocking(self._robot.home_position, speed, should_abort)

    def grip(self) -> None:
        """Close the gripper to grasp the cube."""
        self._robot.closed_gripper()
        self._emit()

    def release(self) -> None:
        """Open the gripper to release the cube."""
        self._robot.open_gripper()
        self._emit()

    @property
    def gripper_closed(self) -> bool:
        return self._robot.gripper_state is GripperState.CLOSED

    # -- Internals -------------------------------------------------------
    def _set_moving(self, moving: bool) -> None:
        self._moving = moving
        self._emit()

    def _emit(self) -> None:
        if self._on_update is not None:
            self._on_update(self.position, self.gripper, self._moving)

    @classmethod
    def _reached(cls, position: Vector3, target: Vector3) -> bool:
        return all(
            abs(p - t) <= cls.REACH_TOLERANCE_MM for p, t in zip(position, target)
        )
