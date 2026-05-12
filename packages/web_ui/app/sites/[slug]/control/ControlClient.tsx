"use client";

import { CheckCircle2, Clock, Radio, RotateCcw, Send, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { authToken, currentUserLabel } from "@/lib/api";
import { fixture } from "@/lib/fixtures";
import { nowTime } from "@/lib/format";

type Step = "issued" | "sent" | "edge" | "confirmed";

export default function ControlClient() {
  const [windowMinutes, setWindowMinutes] = useState(String(fixture.metrics.demandWindowMinutes));
  const [active, setActive] = useState<Step | "idle">("idle");
  const hasCloudSession = typeof window !== "undefined" && Boolean(authToken());
  const userLabel = typeof window !== "undefined" ? currentUserLabel() : "operator";
  const [history, setHistory] = useState([
    { time: "14:23", user: "Marius", type: "set_demand_window", param: "15 min", status: "confirmed", readback: "15 min" },
    { time: "13:51", user: "Johan", type: "set_demand_window", param: "30 min", status: "confirmed", readback: "30 min" }
  ]);

  const steps = useMemo(
    () => [
      { id: "issued" as const, label: "Issued by operator", icon: <Send size={16} /> },
      { id: "sent" as const, label: "Published by cloud relay", icon: <Radio size={16} /> },
      { id: "edge" as const, label: "Edge writes Modbus FC06", icon: <SlidersHorizontal size={16} /> },
      { id: "confirmed" as const, label: "Read-back confirmed", icon: <CheckCircle2 size={16} /> }
    ],
    []
  );

  function applyCommand() {
    setActive("issued");
    window.setTimeout(() => setActive("sent"), 500);
    window.setTimeout(() => setActive("edge"), 1200);
    window.setTimeout(() => {
      setActive("confirmed");
      setHistory((rows) => [
        {
          time: nowTime(),
          user: "Marius",
          type: "set_demand_window",
          param: `${windowMinutes} min`,
          status: "confirmed",
          readback: `${windowMinutes} min`
        },
        ...rows
      ]);
    }, 2100);
  }

  function stepState(id: Step) {
    const order: Step[] = ["issued", "sent", "edge", "confirmed"];
    if (active === "idle") return "";
    const activeIndex = order.indexOf(active);
    const thisIndex = order.indexOf(id);
    if (thisIndex < activeIndex) return "done";
    if (thisIndex === activeIndex) return active === "confirmed" ? "done" : "active";
    return "";
  }

  return (
    <AppShell active="control" dataMode={hasCloudSession ? "cloud" : "fixtures"} userLabel={userLabel}>
      <div className="page-heading">
        <div>
          <h1>Demand window control</h1>
          <p>POC command target: Acuvim L demand sliding window register 0x010C.</p>
        </div>
        <span className="pill warn">command endpoint pending</span>
      </div>

      <div className="grid dashboard-grid">
        <div className="card span-5">
          <div className="card-title">
            <span>Apply demand integration window</span>
            <Clock size={18} />
          </div>
          <div className="form-panel" style={{ marginTop: 16 }}>
            <label>
              <span className="subtext">Window length</span>
              <select className="select" value={windowMinutes} onChange={(e) => setWindowMinutes(e.target.value)}>
                {[1, 5, 10, 15, 30].map((value) => (
                  <option value={value} key={value}>{value} minutes</option>
                ))}
              </select>
            </label>
            <button className="button" onClick={applyCommand} disabled={active !== "idle" && active !== "confirmed"}>
              Apply {windowMinutes} minute window
            </button>
            <p className="subtext">
              The cloud read endpoints are wired for live telemetry. Command issuing stays simulated until the FastAPI command endpoint lands.
            </p>
          </div>
        </div>

        <div className="card span-7">
          <div className="card-title">
            <span>Live command status</span>
            {active === "confirmed" ? <span className="pill ok">confirmed</span> : <span className="pill muted">waiting</span>}
          </div>
          <div className="timeline">
            {steps.map((step) => (
              <div className={`timeline-row ${stepState(step.id)}`} key={step.id}>
                <span className="timeline-dot" />
                <strong className="inline-row">{step.icon} {step.label}</strong>
                <span className="subtext">{stepState(step.id) === "active" ? "in progress" : stepState(step.id) === "done" ? "done" : "pending"}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card span-12">
          <div className="card-title">
            <span>Recent command audit</span>
            <RotateCcw size={18} />
          </div>
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Type</th>
                <th>Param</th>
                <th>Status</th>
                <th>Read-back</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row, index) => (
                <tr key={`${row.time}-${index}`}>
                  <td>{row.time}</td>
                  <td>{row.user}</td>
                  <td>{row.type}</td>
                  <td>{row.param}</td>
                  <td><span className="pill ok">{row.status}</span></td>
                  <td>{row.readback}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
