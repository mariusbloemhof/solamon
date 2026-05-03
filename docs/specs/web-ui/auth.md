# Web UI — auth

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)

Login flow, session management, route protection, logout. Consumes the cloud's auth endpoints from [`../cloud/api-surface.md`](../cloud/api-surface.md) §3.

---

## 1. Stack

| Concern | Choice |
|---------|--------|
| Auth library | **NextAuth (Auth.js v5)** Credentials provider — pin a GA release in `package.json` (Auth.js v5 was in beta/RC for an extended window; verify the chosen version is on `latest`, not `next`/`beta`, before locking) |
| Provider backend | FastAPI `POST /api/v1/auth/login` |
| Session strategy | **JWT** (NextAuth stores the JWT in an HTTP-only encrypted cookie) |
| Session lifetime | 24 hours, matching FastAPI's JWT TTL |
| Refresh strategy | None for MVP — re-login on expiry |

NextAuth in JWT-session mode does NOT store a server-side session. The session cookie carries the encrypted JWT (which contains `sub`, `email`, `tier`, `role`, and the FastAPI access token). Each request decrypts the cookie and reconstructs the session. No DB, no Redis.

## 2. Login flow

```
User → /login
       │
       │ React Hook Form + Zod validates email/password client-side
       ▼
NextAuth signIn("credentials", { email, password })
       │
       ▼
NextAuth Credentials provider's authorize() function:
   POST FastAPI /api/v1/auth/login
   Body: { email, password }
       │
       ├─ FastAPI returns 200 { access_token, expires_in, user } → success path
       │   • Build session JWT containing { sub: user.id, email, tier, role, accessToken }
       │   • Set HTTP-only encrypted cookie "next-auth.session-token"
       │   • Redirect to ?callbackUrl= or "/"
       │
       └─ FastAPI returns 401/422 → throw Error("invalid_credentials")
           • NextAuth surfaces error to /login form
           • Form shows toast "Email or password incorrect"
```

NextAuth route handler at `app/api/auth/[...nextauth]/route.ts`:

```typescript
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(creds) {
        const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(creds),
        });
        if (!res.ok) return null;     // NextAuth treats null as auth failure
        const { access_token, expires_in, user } = await res.json();
        return { ...user, accessToken: access_token, expiresAt: Date.now() + expires_in * 1000 };
      },
    }),
  ],
  pages: { signIn: "/login" },
  session: { strategy: "jwt", maxAge: 24 * 60 * 60 },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.accessToken = user.accessToken;
        token.tier = user.tier;
        token.role = user.role;
        token.expiresAt = user.expiresAt;
      }
      return token;
    },
    async session({ session, token }) {
      session.user.tier = token.tier;
      session.user.role = token.role;
      session.accessToken = token.accessToken as string;
      session.expiresAt = token.expiresAt as number;
      return session;
    },
  },
});
```

## 3. Authenticated requests

Every server-side fetch and every client-side fetch attaches the access token from the session.

Both `apiServer` and `apiClient` return an **SDK-shaped** object — the typed methods are generated from the cloud's OpenAPI by `openapi-typescript` (see [`live-data.md`](live-data.md) §10). The internal fetch wrapper is shared but never exported directly: every call goes through a typed method like `apiServer(session).getSite(slug)`.

```typescript
// lib/api-client.ts
import createClient, { type Client } from "openapi-fetch";
import type { paths } from "./api-schema";

function buildClient(accessToken: string): Client<paths> {
  const base = createClient<paths>({ baseUrl: `${API_BASE}/api/v1` });

  base.use({
    onRequest({ request }) {
      request.headers.set("authorization", `Bearer ${accessToken}`);
      return request;
    },
    onResponse({ response }) {
      if (response.status === 401) {
        // Server context: throw a typed error and let the page's redirect helper take over.
        // Client context: redirect immediately.
        throw new SessionExpiredError();
      }
      return response;
    },
  });

  return base;
}
```

### 3.1 Server-side use

```typescript
import { auth } from "@/auth";

export async function apiServer() {
  const session = await auth();
  if (!session?.accessToken) redirect("/login");
  return buildClient(session.accessToken);
}

// Usage from a page:
const client = await apiServer();
const { data: site } = await client.GET("/sites/{slug}", { params: { path: { slug } } });
```

The page calls `await apiServer()` once and passes the client into `Promise.all` for parallel fetches. (Earlier drafts of this spec showed `apiServer<T>(path, init)` as a generic fetch wrapper — superseded by the SDK shape above.)

### 3.2 Client-side use

```typescript
"use client";
import { useSession } from "next-auth/react";

export function useApiClient() {
  const { data: session } = useSession();
  return useMemo(
    () => session?.accessToken ? buildClient(session.accessToken) : null,
    [session?.accessToken]
  );
}

// Usage in a client component:
const client = useApiClient();
const { data: snapshot } = useQuery({
  queryKey: ["snapshot", device_id],
  queryFn: () => client!.GET("/sites/{slug}/devices/{device_id}/snapshot", { ... }).then(r => r.data),
  enabled: !!client,
});
```

A 401 from any client-side call triggers `window.location.href = "/login?callbackUrl=" + encodeURIComponent(window.location.pathname)` (the `onResponse` interceptor catches the SessionExpiredError and routes there).

### 3.3 WebSocket auth

The browser WebSocket API doesn't support arbitrary headers; we use the `Sec-WebSocket-Protocol` mechanism (per [`../cloud/api-surface.md`](../cloud/api-surface.md) §5.1):

```typescript
const ws = new WebSocket(wsUrl, ["solamon-bearer", session.accessToken]);
```

Server validates the second protocol string as a JWT and either accepts (echoing back `solamon-bearer`) or rejects with close code 1008.

Detail in [`live-data.md`](live-data.md) §4.2.

## 4. Route protection

Next.js middleware (`middleware.ts` at repo root) enforces auth on every route except `/login` and the NextAuth handlers:

```typescript
// middleware.ts
import { auth } from "@/auth";

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const isProtected = !req.nextUrl.pathname.startsWith("/login")
                    && !req.nextUrl.pathname.startsWith("/api/auth");

  if (isProtected && !isLoggedIn) {
    const callbackUrl = encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search);
    return Response.redirect(new URL(`/login?callbackUrl=${callbackUrl}`, req.url));
  }
  if (isLoggedIn && req.nextUrl.pathname === "/login") {
    return Response.redirect(new URL("/", req.url));
  }
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

### 4.1 Role gates

Admin routes require `role === "admin"`. Enforced in the page's server component (and the corresponding API endpoint server-side):

```typescript
// app/admin/profiles/page.tsx
import { auth } from "@/auth";
import { redirect } from "next/navigation";

export default async function AdminProfilesPage() {
  const session = await auth();
  if (session?.user?.role !== "admin") {
    redirect("/");
  }
  // ... fetch and render
}
```

In MVP the only operator role IS `admin`, so the check is academic — but the gate exists for future multi-role.

## 5. Logout

```typescript
// components/UserMenu.tsx
"use client";
import { signOut } from "next-auth/react";

<button onClick={() => signOut({ callbackUrl: "/login" })}>
  Sign out
</button>
```

NextAuth clears the session cookie and redirects to `/login`.

The cloud-side `POST /api/v1/auth/logout` is **not called** in MVP — it's a no-op anyway (per [`../cloud/api-surface.md`](../cloud/api-surface.md) §3.2). When a JWT denylist is added post-MVP, the client also calls `/auth/logout` to invalidate server-side.

## 6. Session expiry handling

Three places where expiry shows up:

1. **`apiServer` 401 in a server component** → redirect to `/login?callbackUrl=...` immediately.
2. **`apiClient` 401 in a client component** → redirect via `window.location.href = "/login?..."`.
3. **WebSocket close code 1008** → trigger a session refresh check; if the session is in fact expired, redirect to login. Otherwise treat as a server-side issue and let the reconnect logic handle it.

NextAuth's `expiresAt` field on the session is also checked client-side — if `Date.now() > session.expiresAt`, the UI redirects to login proactively without waiting for the next API call to fail.

## 7. Security posture

- Session cookie is `Secure; HttpOnly; SameSite=Lax`. Set by NextAuth.
- The encryption key for the JWT cookie is `NEXTAUTH_SECRET` (a 32-byte random env var generated at deploy).
- CSRF protection: NextAuth has built-in CSRF tokens for the credentials POST.
- The access token is never logged; the `signIn` failure path doesn't echo the password back.
- The login form uses `autocomplete="current-password"` so password managers work; doesn't use `autocomplete="off"` (which is widely understood to be hostile).

**XSS exposes the access token.** The session callback exposes `session.accessToken` to client components via `useSession()` — required for `apiClient` and `<WebSocket>` auth. An XSS that lands in any rendered surface (e.g., a Tremor tooltip rendering unsanitised user-supplied content in a future feature) can read `useSession().data.accessToken` and call any API endpoint as the operator. The standard mitigation (HttpOnly cookies for auth) is incompatible with the `Sec-WebSocket-Protocol` mechanism (the JS *needs* the token in memory to construct the WS). For MVP single-tenant single-admin with no untrusted-input render paths this is acceptable; **before adding any feature that renders unsanitised content** (operator notes, comments, free-text fields), revisit. Mitigations short of a full HttpOnly migration: a strict CSP (`default-src 'self'; script-src 'self'`), `dangerouslySetInnerHTML` audit, sanitiser-by-default (DOMPurify or React's auto-escaping never bypassed).

**Clock skew.** The proactive `Date.now() > session.expiresAt` check in §6 trusts the client clock. A client whose clock is wrong by more than the session TTL (24 h) will either redirect-to-login when the session is actually valid, or skip the proactive redirect and fail on the next API call. Acceptable for MVP; not a security issue (the server validates JWT exp independently). Document that the proactive redirect is a UX nicety, not a security boundary.

## 8. MVP-only constraints

- **Single shared admin user** in MVP. No invite flow, no signup, no password reset, no MFA. Marius and Johan share the credentials. When multi-user / RBAC arrives (post-MVP), this layer expands but the NextAuth + Credentials shape stays.
- **Plaintext password in the request body** (over TLS). Cloud-side stores bcrypt hash; the wire transmission is the standard pattern. mTLS / passkeys / SSO are post-MVP.
- **24-hour session.** Long enough to cover a working day without re-login; short enough that a forgotten laptop doesn't stay logged in indefinitely.
- **No login rate-limiting in MVP.** Neither NextAuth nor the cloud's `POST /auth/login` enforces a per-IP or per-account limit (cloud review #6 also flagged this absence cloud-side). With a single shared admin password and a public login URL, an attacker who phishes the URL can brute-force at HTTP latency. Acceptable for the MVP single-tenant deployment; add rate-limiting at Caddy (per-IP `rate_limit` directive) or in FastAPI middleware before adding any second tenant.

## 9. Acceptance criteria

- Hitting `/sites/bench` while logged out → redirect to `/login?callbackUrl=%2Fsites%2Fbench`. After login, redirect back to `/sites/bench`.
- Hitting `/login` while logged in → redirect to `/`.
- Wrong credentials → toast "Email or password incorrect"; no redirect; password field cleared, focus returns to email field.
- Session cookie has `HttpOnly`, `Secure`, `SameSite=Lax` flags (verified in browser DevTools).
- 24 hours after login, the next API call returns 401 and the UI redirects to login.
- Logout clears the session cookie immediately (verified in DevTools); subsequent navigation goes through the protected-route gate.
- Admin pages return to `/` for non-admin users without throwing.

## 10. Cross-references

- [`pages.md`](pages.md) — `/login` page
- [`live-data.md`](live-data.md) §4.2 — WebSocket auth uses the same access token
- [`../cloud/api-surface.md`](../cloud/api-surface.md) §3 — login / logout / me endpoints
