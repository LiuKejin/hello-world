# Solution — Gantry Pick &amp; Place (POC)

A proof-of-concept controller for a 3-axis gantry robot that picks a cube from
**Table A** and places it on **Table B**, with a FastAPI backend driven by a
state machine and a React/TypeScript dashboard.

The emphasis of this POC is **architecture and the core control idea**, not
exhaustive feature coverage.

---

## The big idea

A robot cell is fundamentally three concerns that should not bleed into each
other:

1. **Hardware** — how you actually move the robot (here, `robot_sim`).
2. **Choreography** — the ordered, fault-aware *sequence* of motions.
3. **Transport** — how operators observe and command the cell.

The design keeps these as separate layers with dependencies pointing **inward**
(transport → use cases → hardware), so each layer can be tested and replaced on
its own:

```
 Robot (robot_sim)            hardware simulator (provided)
   └─ RobotController         blocking motion primitives  ── unit-tested, framework-free
         └─ GantryService     use cases + background worker + abort
              ├─ PickPlaceStateMachine   choreography (vention-state-machine)
              ├─ TelemetryHub            thread-safe live snapshot + pub/sub
              ├─ REST router  /api/*     POC dashboard transport
              └─ VentionApp   /rpc/* + telemetry stream  (production transport)
```

The single most important detail of the brief — *“`move_to` must be called
repeatedly until motion is complete”* — is encapsulated **once**, in
`RobotController.move_to_blocking`. No other layer knows the simulator is
non-blocking.

---

## Architecture decisions &amp; trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| **Ports &amp; adapters / layered design** | Hardware, choreography and transport evolve independently; each is testable in isolation. | More files than a single `main.py` — justified for a controller that must stay correct. |
| **Blocking motion on a background worker thread** | `robot_sim` advances in real time; the API thread must stay responsive. One worker + an abort `Event` is the simplest correct model. | Single concurrent operation (correct for one robot). Multi-robot would need a worker pool. |
| **State machine owns the choreography** in `on_enter` callbacks | Directly satisfies the mandate to implement control logic with `vention-state-machine`; transitions/guards/history come for free. | Tightly couples the sequence to the library — mitigated by injecting `RobotController`. |
| **Stable `Phase` enum decoupled from library state strings** | The library reports `"Running_picking"`; the API/UI contract stays stable even if the library changes. | A small mapping table to maintain. |
| **`vention-communication` is the *production* transport; a REST mirror serves the POC** | Both delegate to the **same** `GantryService`, so there is one implementation of the logic. REST keeps the POC frontend dependency-light (no Buf/SDK codegen). | Two transport adapters. The RPC layer is wired but the React app talks to REST. |
| **Telemetry by polling (250 ms) in the POC** | Trivial, robust, no socket lifecycle to manage. | Not push-based; the `telemetry` stream (`replay=True`) is the production path. |
| **Lazy / optional vention imports** | The libraries require **Python 3.10**; the backend still boots, serves status/config and runs the unit tests on any Python. | `Start sequence` returns a clear error (and the UI disables it) when the library is absent. |

### Assumptions

- **Approach height (`safe_z`)**: the tool always retracts to a travel height
  before any XY move, so it never drags the cube across a table. The sequence is
  therefore: above-cube → down → grip → up → above-dest → down → release → up.
- **Coordinates** are millimetres in the robot base frame, `z` up; **speed** is
  mm/s within the simulator's `0..100` window; the envelope is ±1000 mm/axis
  (from `robot_sim`).
- **Home** is a standalone command (default `[0, 0, 0]`), independent of the
  pick-and-place cycle.
- `Stop` is a cooperative abort polled by the in-flight motion.

---

## Backend layout

| File | Responsibility |
|---|---|
| `app/domain.py` | Value objects (`GantryConfig`, `GantrySnapshot`, `Phase`), waypoint derivation, validation. No framework imports. |
| `app/robot_controller.py` | Blocking facade over `robot_sim`; encapsulates the poll-until-complete loop, gripper, homing, abort. |
| `app/telemetry.py` | Thread-safe latest-snapshot store with pub/sub. |
| `app/state_machine.py` | `vention-state-machine` definition; pick-and-place choreography in `on_enter` callbacks. |
| `app/orchestrator.py` | `GantryService` use cases; background worker; abort; config guarding. |
| `app/api.py` | REST mirror of the use cases. |
| `app/comm.py` | `vention-communication` actions + telemetry stream (production transport). |
| `main.py` | Composition root + FastAPI wiring. |
| `tests/` | Unit tests for the controller, domain and service. |

---

## Setup &amp; run

> The vention libraries require **Python 3.10**. The backend boots without them
> (REST status/config + tests still work), but the pick-and-place **sequence**
> needs them.

### Backend

```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1   |   macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload          # http://localhost:8000  (docs at /docs)
```

### Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173 (proxies /api → :8000)
```

### Tests

```bash
cd backend
pytest                             # runs on any Python; no vention libs needed
```

The deterministic core (the `move_to` polling loop, homing, gripper, validation
and the background worker) is covered by **16 passing unit tests** that run
without the vention libraries.

---

## What I would add next (beyond a POC)

- Switch the dashboard to the `vention-communication` telemetry **stream** via a
  generated SDK (push instead of polling).
- A homing state inside the machine and a `DONE` dwell before returning to idle.
- E-stop / fault-reset surfaced in the UI (`reset` trigger already exists).
- Integration tests that exercise the full state machine on Python 3.10 in CI.
