import Link from "next/link";
import { Activity, Gauge, Settings, ShieldCheck, SlidersHorizontal } from "lucide-react";

export function AppShell({
  children,
  active = "dashboard"
}: {
  children: React.ReactNode;
  active?: "dashboard" | "control" | "admin";
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>Solamon</strong>
          <span>Solar Monitor POC</span>
        </div>
        <nav className="nav" aria-label="Main navigation">
          <Link className={active === "dashboard" ? "active" : ""} href="/sites/bench">
            <Gauge size={18} /> Dashboard
          </Link>
          <Link className={active === "control" ? "active" : ""} href="/sites/bench/control">
            <SlidersHorizontal size={18} /> Control
          </Link>
          <Link href="/sites/bench">
            <Activity size={18} /> Devices
          </Link>
          <Link className={active === "admin" ? "active" : ""} href="/sites/bench">
            <Settings size={18} /> Admin
          </Link>
        </nav>
        <div style={{ marginTop: "auto" }} className="subtext">
          Build POC-local
          <br />
          Fixture replay enabled
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <span className="pill ok"><span className="dot" /> Connected</span>
            <span className="pill warn" title="Values are replayed from local fixtures until cloud API is ready.">
              Demo fixtures
            </span>
            <span className="pill muted">bench</span>
          </div>
          <div className="topbar-right">
            <ShieldCheck size={17} color="#10b981" />
            <span className="subtext">admin@bench.local</span>
            <Link className="button secondary" href="/login">Sign out</Link>
          </div>
        </header>
        <section className="content">{children}</section>
      </main>
    </div>
  );
}
