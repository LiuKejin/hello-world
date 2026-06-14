import type { Phase, Status } from "../types";

const PHASE_LABEL: Record<Phase, string> = {
  IDLE: "Idle",
  HOMING: "Homing",
  MOVING_TO_PICK: "Moving to cube",
  PICKING: "Picking",
  MOVING_TO_PLACE: "Moving to destination",
  PLACING: "Placing",
  DONE: "Cycle complete",
  FAULT: "Fault",
};

function fmt(v: number): string {
  return v.toFixed(1);
}

export function Dashboard({ status }: { status: Status }) {
  const { position, gripper, moving, phase, error, config } = status;
  return (
    <div>
      <h2>Telemetry</h2>

      <div className={`state-banner phase-${phase.toLowerCase()}`}>
        <span className="state-label">State</span>
        <span className="state-value">{PHASE_LABEL[phase]}</span>
      </div>

      <dl className="telemetry">
        <dt>Robot position</dt>
        <dd>
          X {fmt(position[0])} &nbsp; Y {fmt(position[1])} &nbsp; Z {fmt(position[2])} mm
        </dd>
        <dt>Gripper</dt>
        <dd>
          <span className={`pill ${gripper === "CLOSED" ? "closed" : "open"}`}>
            {gripper}
          </span>
        </dd>
        <dt>Motion</dt>
        <dd>
          <span className={`pill ${moving ? "moving" : "idle"}`}>
            {moving ? "MOVING" : "IDLE"}
          </span>
        </dd>
        <dt>Cube start</dt>
        <dd>{config.cube_position.map(fmt).join(", ")} mm</dd>
        <dt>Destination</dt>
        <dd>{config.destination.map(fmt).join(", ")} mm</dd>
      </dl>

      {error && <div className="error-box">⚠ {error}</div>}
    </div>
  );
}
