"""
vention-communication transport
================================

Exposes the gantry use cases over ``vention-communication`` as Connect-style
RPC *actions* plus a live telemetry *stream*. This is the intended production
transport: ``app.finalize()`` emits a ``.proto`` from these decorators, from
which typed TypeScript/Python SDKs are generated (via Buf) so the frontend gets
auto-completed, strongly typed calls with no hand-written HTTP code.

It delegates to the same :class:`GantryService` as the REST router, so there is
exactly one implementation of the business logic regardless of transport.

The whole module is optional: it requires Python 3.10 and the vention
libraries. ``build_vention_app`` returns ``None`` when they are unavailable so
the backend still boots with the REST mirror alone.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .domain import Vector3
from .orchestrator import GantryService
from .telemetry import TelemetryHub

try:  # Optional dependency (Python 3.10 + vention-communication).
    from pydantic import BaseModel
    from communication.app import VentionApp
    from communication.decorators import action, stream

    _COMM_AVAILABLE = True
except Exception:  # noqa: BLE001
    _COMM_AVAILABLE = False


def comm_available() -> bool:
    return _COMM_AVAILABLE


if _COMM_AVAILABLE:

    class TelemetryPayload(BaseModel):
        position: Vector3
        gripper: str
        moving: bool
        phase: str
        error: Optional[str] = None

    class ConfigPayload(BaseModel):
        cube_position: Optional[Vector3] = None
        destination: Optional[Vector3] = None
        home_position: Optional[Vector3] = None
        safe_z: Optional[float] = None
        speed: Optional[float] = None

    class CommandPayload(BaseModel):
        success: bool
        message: str

    def build_vention_app(
        service: GantryService,
        telemetry: TelemetryHub,
        name: str = "GantryPickPlace",
    ) -> "VentionApp":
        """Wire the gantry use cases into a finalized ``VentionApp``."""
        app = VentionApp(name=name, emit_proto=True)

        @action()
        async def get_status() -> TelemetryPayload:
            return TelemetryPayload(**telemetry.get().to_dict())

        @action()
        async def set_config(req: ConfigPayload) -> CommandPayload:
            changes = {k: v for k, v in req.model_dump().items() if v is not None}
            return CommandPayload(**service.set_config(**changes).to_dict())

        @action()
        async def home() -> CommandPayload:
            return CommandPayload(**service.home().to_dict())

        @action()
        async def start() -> CommandPayload:
            return CommandPayload(**service.start_sequence().to_dict())

        @action()
        async def stop() -> CommandPayload:
            return CommandPayload(**service.stop().to_dict())

        # `replay=True` so a freshly connected dashboard immediately receives
        # the current cell state instead of waiting for the next tick.
        @stream(name="telemetry", payload=TelemetryPayload, replay=True)
        async def telemetry_stream() -> TelemetryPayload:
            return TelemetryPayload(**telemetry.get().to_dict())

        app.finalize()
        app._telemetry_publisher = telemetry_stream  # used by the publish loop
        return app

    async def publish_telemetry_loop(app: "VentionApp", period_s: float = 0.1) -> None:
        """Broadcast telemetry to all stream subscribers at a fixed cadence."""
        publisher = getattr(app, "_telemetry_publisher", None)
        if publisher is None:
            return
        while True:
            await publisher()
            await asyncio.sleep(period_s)

else:

    def build_vention_app(*_args, **_kwargs):  # type: ignore[misc]
        return None

    async def publish_telemetry_loop(*_args, **_kwargs):  # type: ignore[misc]
        return None
