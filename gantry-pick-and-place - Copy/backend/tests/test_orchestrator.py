"""Tests for the orchestrator service and domain validation.

These exercise the parts that do not require the vention libraries: status
reporting, configuration validation and the background homing worker. The
pick-and-place sequence itself depends on ``vention-state-machine`` (Python
3.10) and is covered structurally by the state-machine module.
"""

import time

import pytest

from app.domain import ConfigError, GantryConfig, Phase, validate_config
from app.orchestrator import GantryService
from app.robot_controller import RobotController
from app.telemetry import TelemetryHub
from robot_sim import Robot


def build_service(initial=(0.0, 0.0, 0.0), home=(0.0, 0.0, 0.0)):
    telemetry = TelemetryHub()
    robot = Robot(initial_position=list(initial), home_position=list(home))
    controller = RobotController(robot, on_update=telemetry.set_motion)
    telemetry.set_motion(controller.position, controller.gripper, controller.moving)
    return GantryService(controller, telemetry)


def wait_until_idle(service: GantryService, timeout_s: float = 5.0):
    deadline = time.time() + timeout_s
    while service.is_busy() and time.time() < deadline:
        time.sleep(0.01)
    assert not service.is_busy(), "service did not finish in time"


# -- Domain validation ---------------------------------------------------
def test_validate_config_rejects_out_of_envelope():
    with pytest.raises(ConfigError):
        validate_config(GantryConfig(cube_position=[9999.0, 0.0, 0.0]))


def test_validate_config_rejects_bad_speed():
    with pytest.raises(ConfigError):
        validate_config(GantryConfig(speed=0))
    with pytest.raises(ConfigError):
        validate_config(GantryConfig(speed=200))


def test_config_derived_waypoints():
    config = GantryConfig(cube_position=[100, 200, 0], safe_z=300)
    assert config.approach_pick == [100, 200, 300]
    assert config.grasp_pick == [100, 200, 0]


# -- Service -------------------------------------------------------------
def test_status_defaults_to_idle():
    service = build_service()
    status = service.get_status()
    assert status["phase"] == Phase.IDLE.value
    assert status["busy"] is False
    assert "config" in status


def test_set_config_valid_and_invalid():
    service = build_service()
    assert service.set_config(speed=50).success is True
    assert service.config.speed == 50
    assert service.set_config(speed=999).success is False


def test_home_moves_robot_to_home():
    service = build_service(initial=(20.0, 0.0, 0.0), home=(0.0, 0.0, 0.0))
    assert service.home().success is True
    wait_until_idle(service)
    status = service.get_status()
    assert status["position"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-6)
    assert status["phase"] == Phase.IDLE.value


def test_cannot_change_config_while_busy():
    service = build_service(initial=(900.0, 0.0, 0.0), home=(0.0, 0.0, 0.0))
    service.home()  # long move keeps the worker busy briefly
    result = service.set_config(speed=10)
    service.stop()
    wait_until_idle(service)
    assert result.success is False
