import type { CommandResult, GantryConfig, Status } from "./types";

// Thin typed client over the REST mirror. In production this would be the
// generated vention-communication SDK; the surface is intentionally identical.
const BASE = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () => fetch(`${BASE}/status`).then(json<Status>),

  setConfig: (changes: Partial<GantryConfig>) =>
    fetch(`${BASE}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }).then(json<CommandResult>),

  home: () => fetch(`${BASE}/home`, { method: "POST" }).then(json<CommandResult>),
  start: () => fetch(`${BASE}/start`, { method: "POST" }).then(json<CommandResult>),
  stop: () => fetch(`${BASE}/stop`, { method: "POST" }).then(json<CommandResult>),
};
