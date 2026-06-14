import type { Status, Vector3 } from "../types";

// Top-down (X–Y) schematic of the work cell. World millimetres are projected
// into the SVG viewbox; world +Y points up, so the SVG Y axis is inverted.
const VIEW = { w: 440, h: 320 };
const WORLD = { xMin: -150, xMax: 850, yMin: -150, yMax: 550 };

function project([x, y]: Vector3): { cx: number; cy: number } {
  const cx = ((x - WORLD.xMin) / (WORLD.xMax - WORLD.xMin)) * VIEW.w;
  const cy = VIEW.h - ((y - WORLD.yMin) / (WORLD.yMax - WORLD.yMin)) * VIEW.h;
  return { cx, cy };
}

function Table({ center, label, tone }: { center: Vector3; label: string; tone: string }) {
  const { cx, cy } = project(center);
  const w = 90;
  const h = 70;
  return (
    <g>
      <rect x={cx - w / 2} y={cy - h / 2} width={w} height={h} rx={6} className={`table ${tone}`} />
      <text x={cx} y={cy - h / 2 - 6} className="table-label">
        {label}
      </text>
    </g>
  );
}

export function GantryView({ status }: { status: Status }) {
  const { position, gripper, config } = status;
  const robot = project(position);
  const cube = project(config.cube_position);
  const holding = gripper === "CLOSED";

  return (
    <div>
      <h2>Work cell (top view)</h2>
      <svg viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} className="cell" role="img" aria-label="Work cell">
        <rect x={0} y={0} width={VIEW.w} height={VIEW.h} className="cell-bg" />

        <Table center={config.cube_position} label="Table A (pick)" tone="a" />
        <Table center={config.destination} label="Table B (place)" tone="b" />

        {/* Cube – hidden once the gripper has grasped it (it rides the tool). */}
        {!holding && <rect x={cube.cx - 9} y={cube.cy - 9} width={18} height={18} className="cube" />}

        {/* Gantry tool / gripper. */}
        <g transform={`translate(${robot.cx} ${robot.cy})`}>
          <circle r={14} className={`tool ${holding ? "holding" : ""}`} />
          {holding && <rect x={-7} y={-7} width={14} height={14} className="cube held" />}
          <line x1={-20} y1={0} x2={20} y2={0} className="crosshair" />
          <line x1={0} y1={-20} x2={0} y2={20} className="crosshair" />
        </g>
      </svg>
      <p className="legend">
        Z (height): <strong>{position[2].toFixed(0)} mm</strong> &middot; gripper{" "}
        <strong>{gripper}</strong>
      </p>
    </div>
  );
}
