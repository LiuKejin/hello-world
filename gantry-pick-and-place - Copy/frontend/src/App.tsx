import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Status } from "./types";
import { Dashboard } from "./components/Dashboard";
import { Controls } from "./components/Controls";
import { GantryView } from "./components/GantryView";

const POLL_MS = 250;

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);

  // Poll telemetry. The production transport is the vention-communication
  // `telemetry` stream; polling keeps the POC dependency-light.
  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const s = await api.getStatus();
        if (active) {
          setStatus(s);
          setConnected(true);
        }
      } catch {
        if (active) setConnected(false);
      }
    };
    tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const notify = (message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3000);
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Gantry Pick &amp; Place</h1>
        <span className={`conn ${connected ? "ok" : "bad"}`}>
          {connected ? "Backend connected" : "Backend unreachable"}
        </span>
      </header>

      {status ? (
        <main className="layout">
          <section className="panel">
            <GantryView status={status} />
          </section>
          <section className="panel">
            <Dashboard status={status} />
          </section>
          <section className="panel">
            <Controls status={status} onResult={(r) => notify(r.message)} />
          </section>
        </main>
      ) : (
        <p className="loading">Waiting for telemetry…</p>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
