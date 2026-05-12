import { Suspense } from "react";
import { LoginClient } from "./LoginClient";

export default function LoginPage() {
  return (
    <main className="login-page">
      <header className="login-topbar">
        <div className="brand">
          <strong>Solamon</strong>
          <span>v0.4</span>
        </div>
        <span className="subtext">Solar Monitor POC</span>
      </header>
      <section className="login-wrap">
        <div className="login-visual">
          <div>
            <div className="eyebrow">Field Assessment Console</div>
            <h1>Live load assessment for solar sites</h1>
            <p>
              Sign in to inspect registered devices and live Acuvim telemetry from field sites.
            </p>
          </div>
          <div className="login-badges">
            <span className="pill ok"><span className="dot" /> Cloud telemetry online</span>
            <span className="pill muted">Bench site</span>
          </div>
          <div className="login-facts">
            <div><strong>Source</strong><span>Acuvim L MQTT</span></div>
            <div><strong>Window</strong><span>30 day capture</span></div>
            <div><strong>Purpose</strong><span>Client sizing</span></div>
          </div>
        </div>
        <section className="login-card">
          <Suspense fallback={<div className="card">Loading sign in...</div>}>
            <LoginClient />
          </Suspense>
        </section>
      </section>
    </main>
  );
}
