"""
REST API
========

A thin HTTP mirror of the :class:`GantryService` use cases. It exists so the
POC dashboard can talk to the backend with zero code generation.

In production the primary transport is ``vention-communication`` (see
``app/comm.py``), which exposes the same operations as typed Connect RPCs plus
a live telemetry stream. This REST surface is the pragmatic, dependency-light
path for the take-home POC; both delegate to the identical service layer, so
there is a single source of business logic.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .domain import Vector3
from .orchestrator import GantryService


class ConfigUpdate(BaseModel):
    """Partial configuration update; every field is optional."""

    cube_position: Vector3 | None = Field(None, description="[x, y, z] mm")
    destination: Vector3 | None = Field(None, description="[x, y, z] mm")
    home_position: Vector3 | None = Field(None, description="[x, y, z] mm")
    safe_z: float | None = Field(None, description="Travel height in mm")
    speed: float | None = Field(None, gt=0, le=100, description="mm/s")

    def changes(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


def create_router(service: GantryService) -> APIRouter:
    router = APIRouter()

    @router.get("/status", summary="Live telemetry + current configuration")
    async def get_status() -> dict:
        return service.get_status()

    @router.put("/config", summary="Update cube / destination / motion settings")
    async def update_config(update: ConfigUpdate) -> dict:
        return service.set_config(**update.changes()).to_dict()

    @router.post("/home", summary="Home the robot (move to home position)")
    async def home() -> dict:
        return service.home().to_dict()

    @router.post("/start", summary="Start the pick-and-place sequence")
    async def start() -> dict:
        return service.start_sequence().to_dict()

    @router.post("/stop", summary="Abort the current motion")
    async def stop() -> dict:
        return service.stop().to_dict()

    return router
