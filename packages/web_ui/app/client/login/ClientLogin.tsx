"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { loginToCloud } from "@/lib/api";

export function ClientLogin() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");

    try {
      if (!email.includes("@") || !password) {
        throw new Error("Email or password incorrect");
      }
      await loginToCloud(email, password);
      router.push(params.get("callbackUrl") ?? "/client/sites/bench");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not sign in");
      setBusy(false);
    }
  }

  return (
    <main className="client-login">
      <section className="client-login-panel">
        <div className="client-login-copy">
          <span className="client-mark">Solamon</span>
          <h1>Live Energy Assessment</h1>
          <p>Sign in to view your site assessment. Measurement data updates as it arrives from site.</p>
        </div>

        <form className="client-login-form" onSubmit={submit}>
          <label>
            <span>Email</span>
            <input className="input" name="email" type="email" autoComplete="username" />
          </label>
          <label>
            <span>Password</span>
            <input className="input" name="password" type="password" autoComplete="current-password" />
          </label>
          {error ? <div className="pill warn">{error}</div> : null}
          <button className="button" disabled={busy} type="submit">
            {busy ? "Signing in..." : "Sign in"}
          </button>
          <p className="subtext">Read-only access. No control actions are available from this view.</p>
        </form>
      </section>
    </main>
  );
}
