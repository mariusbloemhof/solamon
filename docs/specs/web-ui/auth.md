# Web UI — auth

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)

Login flow, session management, route protection, logout. Consumes the cloud's auth endpoints from [`../cloud/api-surface.md`](../cloud/api-surface.md) §3.

---

## 1. Stack

| Concern | Choice |
|---------|--------|
| Auth library | **NextAuth (Auth.js v5)** Credentials provider |
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

### 3.1 Server-side fetch

```typescript
// lib/api-client.ts
import { auth } from "@/auth";

export async function apiServer<T>(path: string, init?: RequestInit): Promise<T> {
  const session = await auth();
  if (!session?.accessToken) throw new Error("not_authenticated");

  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      authorization: `Bearer ${session.accessToken}`,
    },
  });
  if (res.status === 401) {
    // Session expired — redirect to /login
    redirect("/login?callbackUrl=" + encodeURIComponent(currentUrl()));
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}
```

### 3.2 Client-side fetch

```typescript
"use client";
import { useSession } from "next-auth/react";

export function useApiClient() {
  const { data: session } = useSession();
  return useMemo(() => ({
    fetch: async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const res = await fetch(`${API_BASE}/api/v1${path}`, {
        ...init,
        headers: {
          ...init?.headers,
          authorization: `Bearer ${session?.accessToken ?? ""}`,
        },
      });
      if (res.status === 401) {
        // Redirect to login
        window.location.href = "/login?callbackUrl=" + encodeURIComponent(window.location.pathname);
      }
      if (!res.ok) throw new ApiError(res.status, await res.text());
      return res.json();
    },
  }), [session?.accessToken]);
}
```

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

## 8. MVP-only constraints

- **Single shared admin user** in MVP. No invite flow, no signup, no password reset, no MFA. Marius and Johan share the credentials. When multi-user / RBAC arrives (post-MVP), this layer expands but the NextAuth + Credentials shape stays.
- **Plaintext password in the request body** (over TLS). Cloud-side stores bcrypt hash; the wire transmission is the standard pattern. mTLS / passkeys / SSO are post-MVP.
- **24-hour session.** Long enough to cover a working day without re-login; short enough that a forgotten laptop doesn't stay logged in indefinitely.

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
