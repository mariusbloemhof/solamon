import { Suspense } from "react";
import { LoginClient } from "./LoginClient";

export default function LoginPage() {
  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="brand">
          <strong>Solamon</strong>
          <span>Solar Monitor POC</span>
        </div>
        <div>
          <h1 style={{ fontSize: 46, margin: 0, letterSpacing: 0 }}>Live load assessment for solar sites</h1>
          <p style={{ maxWidth: 620, lineHeight: 1.6, color: "#dbeafe" }}>
            Revenue-grade Acuvim data, edge health, demand control, and audit-ready command state in one operator console.
          </p>
        </div>
        <div className="inline-row">
          <span className="pill ok"><span className="dot" /> Fixture cloud online</span>
          <span className="pill warn">POC rehearsal</span>
        </div>
      </section>
      <section className="login-card">
        <Suspense fallback={<div className="card">Loading sign in...</div>}>
          <LoginClient />
        </Suspense>
      </section>
    </main>
  );
}
