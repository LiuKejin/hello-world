import { useEffect, useState } from "react";
import { api } from "../api";
import type { CommandResult, Status, Vector3 } from "../types";

interface Props {
  status: Status;
  onResult: (result: CommandResult) => void;
}

// Editable XYZ row. Kept controlled by the parent so it re-syncs with the
// backend config whenever the operator is not actively editing.
function VectorInput({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: Vector3;
  disabled: boolean;
  onChange: (v: Vector3) => void;
}) {
  return (
    <div className="vector-input">
      <label>{label}</label>
      <div className="axes">
        {(["X", "Y", "Z"] as const).map((axis, i) => (
          <input
            key={axis}
            type="number"
            aria-label={`${label} ${axis}`}
            value={value[i]}
            disabled={disabled}
            onChange={(e) => {
              const next = [...value] as Vector3;
              next[i] = Number(e.target.value);
              onChange(next);
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function Controls({ status, onResult }: Props) {
  const { busy, config } = status;
  const [cube, setCube] = useState<Vector3>(config.cube_position);
  const [dest, setDest] = useState<Vector3>(config.destination);
  const [speed, setSpeed] = useState<number>(config.speed);

  // Re-sync local form with backend config while idle (e.g. after a reset).
  useEffect(() => {
    if (!busy) {
      setCube(config.cube_position);
      setDest(config.destination);
      setSpeed(config.speed);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  const run = (p: Promise<CommandResult>) => p.then(onResult).catch((e) => onResult({ success: false, message: String(e) }));

  const applyConfig = () =>
    run(api.setConfig({ cube_position: cube, destination: dest, speed }));

  return (
    <div>
      <h2>Controls</h2>

      <fieldset disabled={busy} className="config">
        <VectorInput label="Cube start" value={cube} disabled={busy} onChange={setCube} />
        <VectorInput label="Destination" value={dest} disabled={busy} onChange={setDest} />
        <div className="vector-input">
          <label>Speed (mm/s)</label>
          <input
            type="number"
            min={1}
            max={100}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          />
        </div>
        <button className="btn" onClick={applyConfig}>
          Apply configuration
        </button>
      </fieldset>

      <div className="actions">
        <button className="btn secondary" disabled={busy} onClick={() => run(api.home())}>
          Home
        </button>
        <button
          className="btn primary"
          disabled={busy || !status.state_machine_available}
          onClick={() => run(api.start())}
        >
          Start sequence
        </button>
        <button className="btn danger" disabled={!busy} onClick={() => run(api.stop())}>
          Stop
        </button>
      </div>

      {!status.state_machine_available && (
        <p className="hint">
          Sequence disabled: vention-state-machine unavailable (requires Python 3.10).
        </p>
      )}
    </div>
  );
}
