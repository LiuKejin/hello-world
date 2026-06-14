export type Vector3 = [number, number, number];

export type Phase =
  | "IDLE"
  | "HOMING"
  | "MOVING_TO_PICK"
  | "PICKING"
  | "MOVING_TO_PLACE"
  | "PLACING"
  | "DONE"
  | "FAULT";

export interface GantryConfig {
  cube_position: Vector3;
  destination: Vector3;
  home_position: Vector3;
  safe_z: number;
  speed: number;
}

export interface Status {
  position: Vector3;
  gripper: "OPEN" | "CLOSED";
  moving: boolean;
  phase: Phase;
  error: string | null;
  busy: boolean;
  config: GantryConfig;
  state_machine_available: boolean;
}

export interface CommandResult {
  success: boolean;
  message: string;
}
