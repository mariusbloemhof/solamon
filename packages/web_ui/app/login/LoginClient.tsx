"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { apiBase, loginToCloud, setApiBase } from "@/lib/api";

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

  return (
    <form className="login-form" onSubmit={submit}>
      <div>
        <div className="eyebrow">Operator Access</div>
        <h2>Sign in</h2>
        <p className="subtext">Use a cloud account with access to registered live devices.</p>
      </div>
      <div className="login-actions-row">
        <button
          className="button secondary"
          type="button"
          onClick={() => {
            const form = document.querySelector<HTMLFormElement>(".login-form");
            setField(form, "email", "admin@cloud.amendi.dev");
            setField(form, "apiBase", "/api/v1");
          }}
        >
          Cloud
        </button>
      </div>
      <div className="grid login-fields">
        <label>
          <span className="subtext">Email</span>
          <input className="input" name="email" type="email" autoComplete="username" defaultValue="admin@cloud.amendi.dev" />
        </label>
        <label>
          <span className="subtext">Password</span>
          <input className="input" name="password" type="password" autoComplete="current-password" placeholder="Cloud admin password" />
        </label>
        <label>
          <span className="subtext">Cloud API base</span>
          <input className="input" name="apiBase" defaultValue={apiBase()} placeholder="/api/v1" />
          <span className="subtext">Default proxies to https://cloud.amendi.dev/api/v1 in local dev.</span>
        </label>
        {error ? <div className="pill warn">{error}</div> : null}
        <button className="button" disabled={busy} type="submit">
          {busy ? "Signing in..." : "Sign in to cloud"}
        </button>
      </div>
    </form>
  );
}

function setField(form: HTMLFormElement | null, name: string, value: string): void {
  const field = form?.elements.namedItem(name);
  if (field instanceof HTMLInputElement) {
    field.value = value;
  }
}
