"""Unit tests for the framework-free robot controller.

These run on any Python version because they only depend on ``robot_sim`` and
the standard library. They prove the core robotics behaviour: the repeated
``move_to`` polling loop, gripper control, homing and error handling.
"""

import pytest

from app.robot_controller import RobotController, RobotError
from robot_sim import GripperState, Robot


def make_controller(initial=(0.0, 0.0, 0.0), home=(0.0, 0.0, 0.0)):
    robot = Robot(initial_position=list(initial), home_position=list(home))
    return RobotController(robot)


def test_move_to_blocking_reaches_target():
    controller = make_controller()
    result = controller.move_to_blocking([10.0, 0.0, 0.0], speed=100)
    assert result == pytest.approx([10.0, 0.0, 0.0], abs=1e-6)
    assert controller.moving is False


def test_move_multi_axis_reaches_target():
    controller = make_controller()
    controller.move_to_blocking([8.0, -6.0, 4.0], speed=100)
    assert controller.position == pytest.approx([8.0, -6.0, 4.0], abs=1e-6)


def test_already_at_target_returns_immediately():
    controller = make_controller(initial=(5.0, 5.0, 5.0))
    assert controller.move_to_blocking([5.0, 5.0, 5.0], speed=50) == [5.0, 5.0, 5.0]


def test_grip_and_release():
    controller = make_controller()
    assert controller.gripper == "OPEN"
    controller.grip()
    assert controller.gripper == GripperState.CLOSED.name
    assert controller.gripper_closed is True
    controller.release()
    assert controller.gripper == "OPEN"
    assert controller.gripper_closed is False


def test_home_returns_to_home_position():
    controller = make_controller(initial=(15.0, 0.0, 0.0), home=(0.0, 0.0, 0.0))
    controller.home(speed=100)
    assert controller.position == pytest.approx([0.0, 0.0, 0.0], abs=1e-6)


def test_invalid_speed_raises():
    controller = make_controller()
    with pytest.raises(RobotError):
        controller.move_to_blocking([10.0, 0.0, 0.0], speed=0)
    with pytest.raises(RobotError):
        controller.move_to_blocking([10.0, 0.0, 0.0], speed=150)


def test_out_of_range_target_raises():
    controller = make_controller()
    with pytest.raises(RobotError):
        controller.move_to_blocking([5000.0, 0.0, 0.0], speed=50)


def test_abort_stops_motion():
    controller = make_controller()
    with pytest.raises(RobotError):
        # Long move, aborted on the very first poll.
        controller.move_to_blocking([900.0, 0.0, 0.0], speed=1, should_abort=lambda: True)
    assert controller.moving is False


def test_on_update_is_called():
    updates = []
    robot = Robot()
    controller = RobotController(
        robot, on_update=lambda pos, grip, moving: updates.append((list(pos), grip, moving))
    )
    controller.move_to_blocking([6.0, 0.0, 0.0], speed=100)
    assert updates, "expected at least one telemetry update"
    assert updates[-1][2] is False  # final update reports motion stopped
