"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { apiBase, loginToCloud, setApiBase, useDemoAuth } from "@/lib/api";

export function LoginClient() {
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
    const base = String(data.get("apiBase") ?? "");
    try {
      if (!email.includes("@") || password.length < 1) {
        throw new Error("Email or password incorrect");
      }
      setApiBase(base);
      await loginToCloud(email, password);
      router.push(params.get("callbackUrl") ?? "/sites/bench");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Cloud login failed");
      setBusy(false);
    }
  }

  function continueWithFixtures() {
    useDemoAuth("demo@bench.local");
    router.push(params.get("callbackUrl") ?? "/sites/bench");
  }

  return (
    <form onSubmit={submit}>
      <h2 style={{ marginTop: 0 }}>Sign in</h2>
      <p className="subtext">Use a cloud account for live sites, or continue with fixtures for offline demos.</p>
      <div className="grid" style={{ gap: 12, marginTop: 20 }}>
        <label>
          <span className="subtext">Email</span>
          <input className="input" name="email" type="email" autoComplete="username" defaultValue="admin@bench.local" />
        </label>
        <label>
          <span className="subtext">Password</span>
          <input className="input" name="password" type="password" autoComplete="current-password" defaultValue="hunter2" />
        </label>
        <label>
          <span className="subtext">Cloud API base</span>
          <input className="input" name="apiBase" defaultValue={apiBase()} placeholder="/api/v1" />
        </label>
        {error ? <div className="pill warn">{error}</div> : null}
        <button className="button" disabled={busy} type="submit">
          {busy ? "Signing in..." : "Sign in to cloud"}
        </button>
        <button className="button secondary" disabled={busy} type="button" onClick={continueWithFixtures}>
          Continue with fixtures
        </button>
      </div>
    </form>
  );
}
