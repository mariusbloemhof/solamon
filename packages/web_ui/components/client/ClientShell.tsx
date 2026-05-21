import { RadioTower } from "lucide-react";
import type { ReactNode } from "react";

export function ClientShell({
  children,
  siteName,
  status,
  lastSeenLabel
}: {
  children: ReactNode;
  siteName: string;
  status: "live" | "delayed" | "offline";
  lastSeenLabel: string;
}) {
  return (
    <main className="client-page">
      <header className="client-topbar">
        <div className="client-brand">
          <strong>Solamon</strong>
          <span>Energy assessment</span>
        </div>
        <div className="client-topbar-right">
          <span className="client-site-name">{siteName}</span>
          <span className={`pill ${status === "live" ? "ok" : status === "delayed" ? "warn" : "muted"}`}>
            <RadioTower size={14} /> {status === "live" ? "Live" : status === "delayed" ? "Delayed" : "No recent readings"}
          </span>
          <span className="pill muted">Last received {lastSeenLabel}</span>
        </div>
      </header>
      {children}
    </main>
  );
}
