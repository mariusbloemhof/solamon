import Link from "next/link";
import {
  Activity,
  Bell,
  ChevronDown,
  ClipboardList,
  Gauge,
  Settings,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";

export function AppShell({
  children,
  active = "dashboard",
  dataMode = "offline",
  userLabel = "operator"
}: {
  children: React.ReactNode;
  active?: "dashboard" | "assessment" | "control" | "admin";
  dataMode?: "cloud" | "offline";
  userLabel?: string;
}) {
  const hasLiveData = dataMode === "cloud";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>Solamon</strong>
          <span>v0.4</span>
        </div>
        <div className="site-picker">
          <span className="site-status-dot" />
          <div className="site-meta">
            <div className="site-name">Bench Energy</div>
            <div className="site-loc">Field assessment</div>
          </div>
          <ChevronDown size={15} />
        </div>
        <nav className="nav" aria-label="Main navigation">
          <span className="nav-section-label">Site</span>
          <Link className={active === "dashboard" ? "active" : ""} href="/sites/bench">
            <Gauge size={18} /> Dashboard
            <span className="count">live</span>
          </Link>
          <Link className={active === "assessment" ? "active" : ""} href="/sites/bench/assessment">
            <ClipboardList size={18} /> Assessment
            <span className="count">30d</span>
          </Link>
          <Link className={active === "control" ? "active" : ""} href="/sites/bench/control">
            <SlidersHorizontal size={18} /> Control
          </Link>
          <Link href="/sites/bench">
            <Activity size={18} /> Devices
          </Link>
          <Link href="/sites/bench">
            <Bell size={18} /> Events
          </Link>
          <span className="nav-section-label">Workspace</span>
          <Link className={active === "admin" ? "active" : ""} href="/sites/bench">
            <Settings size={18} /> Admin
          </Link>
        </nav>
        <div className="sidebar-footer">
          <div className="stat-grid">
            <span>uptime</span><b>99.7%</b>
            <span>last sync</span><b>{hasLiveData ? "live" : "offline"}</b>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <span className="subtext">ops / bench / overview</span>
            <span className={hasLiveData ? "pill ok" : "pill warn"}>
              <span className="dot" /> {hasLiveData ? "Live cloud data" : "No live data"}
            </span>
            <span className="pill muted">bench</span>
          </div>
          <div className="topbar-right">
            <ShieldCheck size={17} color="#10b981" />
            <span className="subtext">{userLabel}</span>
            <Link className="button secondary" href="/login">Sign out</Link>
          </div>
        </header>
        <section className="content">{children}</section>
      </main>
    </div>
  );
}
