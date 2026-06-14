"""
Pick-and-place state machine
============================

The robot's control logic, expressed declaratively with
``vention-state-machine``.

Design intent
-------------
The state machine is the *single source of truth for "what phase are we in"*
and the place where the pick-and-place choreography lives. Each state's
``on_enter`` callback performs one blocking phase of work through the injected
:class:`RobotController`, then fires the trigger that advances to the next
state. Because ``trigger`` is synchronous, a single ``trigger("start")`` walks
the whole cycle to completion; the orchestrator runs that call on a background
worker thread so the API stays responsive.

The sequence (from the exercise brief)::

    ready
      └─start────────────▶ moving_to_pick   (travel above the cube)
            └─approached──▶ picking          (lower → close gripper → lift)
                  └─picked─▶ moving_to_place (travel above the destination)
                        └──▶ placing         (lower → open gripper → lift)
                              └─placed──────▶ ready (cycle complete)

Any hardware error transitions to the library's built-in ``fault`` state with a
human-readable message, which the dashboard surfaces.

Requires Python 3.10 and ``vention-state-machine``; the orchestrator imports
this module lazily so the rest of the backend remains usable without it.
"""

from __future__ import annotations

from typing import Callable

from state_machine.core import BaseTriggers, StateMachine
from state_machine.decorators import on_enter_state, on_state_change
from state_machine.defs import State, StateGroup, Trigger

from .domain import GantryConfig, Phase
from .robot_controller import AbortCheck, RobotController, RobotError
from .telemetry import TelemetryHub


# -- Declarative state/trigger definitions -------------------------------
class Running(StateGroup):
    """Active phases of a single pick-and-place cycle.

    Leaf state names must not contain ``_`` because the underlying
    ``transitions`` library uses ``_`` as its hierarchy separator (so a state
    called ``moving_to_pick`` would be misparsed as nested ``moving/to/pick``).
    We use camelCase leaf names; the full library state string is then
    ``Running_movingToPick`` etc.
    """

    movingToPick: State = State()
    picking: State = State()
    movingToPlace: State = State()
    placing: State = State()


class States:
    running = Running()


class Triggers:
    start = Trigger("start")
    approached_pick = Trigger("approached_pick")
    picked = Trigger("picked")
    approached_place = Trigger("approached_place")
    placed = Trigger("placed")


TRANSITIONS = [
    Triggers.start.transition("ready", States.running.movingToPick),
    Triggers.approached_pick.transition(
        States.running.movingToPick, States.running.picking
    ),
    Triggers.picked.transition(
        States.running.picking, States.running.movingToPlace
    ),
    Triggers.approached_place.transition(
        States.running.movingToPlace, States.running.placing
    ),
    Triggers.placed.transition(States.running.placing, "ready"),
]


# Maps library-internal state strings to the stable, transport-facing Phase.
_STATE_TO_PHASE = {
    "ready": Phase.IDLE,
    "fault": Phase.FAULT,
    "Running_movingToPick": Phase.MOVING_TO_PICK,
    "Running_picking": Phase.PICKING,
    "Running_movingToPlace": Phase.MOVING_TO_PLACE,
    "Running_placing": Phase.PLACING,
}


class PickPlaceStateMachine(StateMachine):
    """Drives one pick-and-place cycle through the injected controller."""

    def __init__(
        self,
        controller: RobotController,
        config: GantryConfig,
        telemetry: TelemetryHub,
        should_abort: AbortCheck | None = None,
    ) -> None:
        super().__init__(
            states=States,
            transitions=TRANSITIONS,
            enable_last_state_recovery=False,
            # Process triggers sequentially. Each phase callback fires the next
            # trigger from inside on_enter; queued mode lets the current
            # transition finish before the next is handled, so state-change
            # callbacks run in linear order (and the final phase is IDLE, not
            # the outermost transition unwinding last).
            queued=True,
        )
        self._controller = controller
        self._config = config
        self._telemetry = telemetry
        self._should_abort: Callable[[], bool] = should_abort or (lambda: False)

    # -- Phase callbacks -------------------------------------------------
    @on_enter_state(States.running.movingToPick)
    def _enter_moving_to_pick(self, _) -> None:
        self._guarded(
            lambda: self._controller.move_to_blocking(
                self._config.approach_pick, self._config.speed, self._should_abort
            ),
            next_trigger=Triggers.approached_pick.name,
        )

    @on_enter_state(States.running.picking)
    def _enter_picking(self, _) -> None:
        def pick() -> None:
            self._controller.move_to_blocking(
                self._config.grasp_pick, self._config.speed, self._should_abort
            )
            self._controller.grip()
            self._controller.move_to_blocking(
                self._config.approach_pick, self._config.speed, self._should_abort
            )

        self._guarded(pick, next_trigger=Triggers.picked.name)

    @on_enter_state(States.running.movingToPlace)
    def _enter_moving_to_place(self, _) -> None:
        self._guarded(
            lambda: self._controller.move_to_blocking(
                self._config.approach_place, self._config.speed, self._should_abort
            ),
            next_trigger=Triggers.approached_place.name,
        )

    @on_enter_state(States.running.placing)
    def _enter_placing(self, _) -> None:
        def place() -> None:
            self._controller.move_to_blocking(
                self._config.grasp_place, self._config.speed, self._should_abort
            )
            self._controller.release()
            self._controller.move_to_blocking(
                self._config.approach_place, self._config.speed, self._should_abort
            )

        self._guarded(place, next_trigger=Triggers.placed.name)

    @on_state_change
    def _publish_phase(self, _old: str, new_state: str, _trigger: str) -> None:
        """Mirror every transition into the telemetry hub for the dashboard."""
        phase = _STATE_TO_PHASE.get(new_state, Phase.IDLE)
        if phase is not Phase.FAULT:
            self._telemetry.set_phase(phase.value, error=None)

    # -- Helpers ---------------------------------------------------------
    def _guarded(self, action: Callable[[], None], next_trigger: str) -> None:
        """Run one phase; on any robot error, divert to the fault state."""
        try:
            action()
        except RobotError as exc:
            self._telemetry.set_phase(Phase.FAULT.value, error=str(exc))
            self.trigger(BaseTriggers.TO_FAULT.value)
            return
        self.trigger(next_trigger)
