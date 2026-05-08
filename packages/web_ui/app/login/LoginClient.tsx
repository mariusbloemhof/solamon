"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

export function LoginClient() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");
    window.setTimeout(() => {
      if (!email.includes("@") || password.length < 1) {
        setError("Email or password incorrect");
        setBusy(false);
        return;
      }
      window.localStorage.setItem("solamon-demo-auth", "true");
      router.push(params.get("callbackUrl") ?? "/sites/bench");
    }, 220);
  }

  return (
    <form onSubmit={submit}>
      <h2 style={{ marginTop: 0 }}>Sign in</h2>
      <p className="subtext">Use any email and password for this local fixture build.</p>
      <div className="grid" style={{ gap: 12, marginTop: 20 }}>
        <label>
          <span className="subtext">Email</span>
          <input className="input" name="email" type="email" autoComplete="username" defaultValue="admin@bench.local" />
        </label>
        <label>
          <span className="subtext">Password</span>
          <input className="input" name="password" type="password" autoComplete="current-password" defaultValue="hunter2" />
        </label>
        {error ? <div className="pill warn">{error}</div> : null}
        <button className="button" disabled={busy} type="submit">
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </div>
    </form>
  );
}
