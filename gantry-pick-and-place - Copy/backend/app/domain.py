"""
Domain model
============

Pure, framework-free description of the gantry cell. Nothing in this module
imports FastAPI, the vention libraries or ``robot_sim``. Keeping the domain
isolated means the rest of the system depends on small, well typed value
objects instead of on transport or hardware details.

Coordinates are millimetres in the robot base frame: ``[x, y, z]`` with ``z``
pointing up. ``speed`` is in mm/s and must stay within the simulator's
``0..100`` window.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

Vector3 = list[float]  # [x, y, z] in millimetres


# Robot envelope, mirrored from robot_sim.Robot.robot_limits.
AXIS_LIMIT_MM = 1000.0
SPEED_MIN = 0.0
SPEED_MAX = 100.0


class Phase(str, Enum):
    """Friendly, transport-facing names for the sequence lifecycle.

    These are decoupled from the underlying state-machine library's internal
    state strings (e.g. ``"Running_picking"``) so the API contract stays stable
    even if the orchestration library changes.
    """

    IDLE = "IDLE"
    HOMING = "HOMING"
    MOVING_TO_PICK = "MOVING_TO_PICK"
    PICKING = "PICKING"
    MOVING_TO_PLACE = "MOVING_TO_PLACE"
    PLACING = "PLACING"
    DONE = "DONE"
    FAULT = "FAULT"


@dataclass(frozen=True)
class GantryConfig:
    """Operator-configurable parameters for a pick-and-place cycle."""

    cube_position: Vector3 = field(default_factory=lambda: [200.0, 200.0, 0.0])
    destination: Vector3 = field(default_factory=lambda: [600.0, 200.0, 0.0])
    home_position: Vector3 = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # Travel height the tool retracts to before any XY move, so it never drags
    # the cube across a table.
    safe_z: float = 300.0
    speed: float = 80.0

    def replace(self, **changes) -> "GantryConfig":
        """Return a copy with the given fields overridden (validated)."""
        return validate_config(replace(self, **changes))

    # Derived waypoints for the pick-and-place sequence -------------------
    @property
    def approach_pick(self) -> Vector3:
        return [self.cube_position[0], self.cube_position[1], self.safe_z]

    @property
    def grasp_pick(self) -> Vector3:
        return list(self.cube_position)

    @property
    def approach_place(self) -> Vector3:
        return [self.destination[0], self.destination[1], self.safe_z]

    @property
    def grasp_place(self) -> Vector3:
        return list(self.destination)


class ConfigError(ValueError):
    """Raised when a requested configuration is physically invalid."""


def _validate_point(name: str, point: Vector3) -> None:
    if len(point) != 3:
        raise ConfigError(f"{name} must have exactly 3 coordinates, got {point!r}")
    for axis, value in enumerate(point):
        if not -AXIS_LIMIT_MM <= value <= AXIS_LIMIT_MM:
            raise ConfigError(
                f"{name} axis {axis} value {value} is outside the robot envelope "
                f"[-{AXIS_LIMIT_MM}, {AXIS_LIMIT_MM}] mm"
            )


def validate_config(config: GantryConfig) -> GantryConfig:
    """Validate a config against the robot envelope and speed window.

    Validation lives in the domain (a system boundary) rather than scattered
    through the API or state machine, so every path that mutates configuration
    is protected by the same rules.
    """
    _validate_point("cube_position", config.cube_position)
    _validate_point("destination", config.destination)
    _validate_point("home_position", config.home_position)
    if not -AXIS_LIMIT_MM <= config.safe_z <= AXIS_LIMIT_MM:
        raise ConfigError(
            f"safe_z {config.safe_z} is outside the robot envelope"
        )
    if not SPEED_MIN < config.speed <= SPEED_MAX:
        raise ConfigError(
            f"speed {config.speed} must be within ({SPEED_MIN}, {SPEED_MAX}] mm/s"
        )
    return config


@dataclass
class GantrySnapshot:
    """A single, serialisable view of the whole cell at one instant.

    This is the payload the dashboard renders and the telemetry stream emits.
    """

    position: Vector3
    gripper: str  # "OPEN" | "CLOSED"
    moving: bool
    phase: str  # one of Phase
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "position": list(self.position),
            "gripper": self.gripper,
            "moving": self.moving,
            "phase": self.phase,
            "error": self.error,
        }
