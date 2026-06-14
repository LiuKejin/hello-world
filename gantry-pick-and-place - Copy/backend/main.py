"""
Application entry point
=======================

Composition root: builds the object graph (robot -> controller -> telemetry ->
service) and wires the transports onto a single FastAPI app.

    Robot (robot_sim)            hardware simulator (provided)
      └─ RobotController         blocking motion primitives
            └─ GantryService     use cases, background worker
                 ├─ REST router  /api/*          (POC dashboard)
                 └─ VentionApp    /rpc/*  +stream (production transport)

Run:  uvicorn main:app --reload
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import create_router
from app.comm import build_vention_app, comm_available, publish_telemetry_loop
from app.orchestrator import GantryService
from app.robot_controller import RobotController
from app.telemetry import TelemetryHub
from robot_sim import Robot

# -- Object graph --------------------------------------------------------
telemetry = TelemetryHub()
robot = Robot()
controller = RobotController(robot, on_update=telemetry.set_motion)
service = GantryService(controller, telemetry)

# Seed telemetry with the robot's actual starting pose.
telemetry.set_motion(controller.position, controller.gripper, controller.moving)

# Optional typed RPC + telemetry stream transport.
vention_app = build_vention_app(service, telemetry)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    publish_task = None
    if vention_app is not None:
        publish_task = asyncio.create_task(publish_telemetry_loop(vention_app))
    try:
        yield
    finally:
        if publish_task is not None:
            publish_task.cancel()


app = FastAPI(
    title="Gantry Pick & Place API",
    version="1.0.0",
    description="3-axis gantry pick-and-place controller (POC).",
    lifespan=lifespan,
)

# Permissive CORS for the local Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(create_router(service), prefix="/api", tags=["Gantry"])


@app.get("/health", tags=["Meta"])
async def health() -> dict:
    return {
        "status": "healthy",
        "vention_communication": comm_available(),
        "state_machine": service.get_status()["state_machine_available"],
    }


# Mount the vention-communication app LAST when available. VentionApp is itself
# a FastAPI application that serves the Connect RPC routes under /rpc (plus the
# telemetry stream). Mounting at "/" must come after our own routes so /api/*
# and /health match first; only unmatched paths (e.g. /rpc/*) fall through.
if vention_app is not None:
    app.mount("/", vention_app)
