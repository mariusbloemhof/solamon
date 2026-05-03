# Web UI — live-data flow

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)

The render pipeline: how data flows from the FastAPI server, into the page, and stays fresh as new readings arrive over WebSocket.

---

## 1. Three sources of data

| Source | Used for | Mechanism |
|--------|----------|-----------|
| **Server fetch in RSC** | Initial page render — page metadata, snapshot, command history | Direct `fetch()` from the page's server component, with the operator's session cookie forwarded |
| **Client fetch via TanStack Query** | Interactive queries — chart data ranges, search filters, paginated lists | `useQuery({ queryKey, queryFn })`; staleTime tuned per query |
| **WebSocket** | Live updates — every reading, snapshot, heartbeat, command transition | Native browser WebSocket; one connection per device-detail subscription, one per active command |

The flow:

```
                                                  ┌────────────────────────────┐
                                                  │  PAGE (server component)   │
                                                  │  Initial fetch:            │
                                                  │  - GET /sites/{slug}       │
                                                  │  - GET .../snapshot        │
                                                  │  - GET .../commands?limit  │
                                                  └──────────────┬─────────────┘
                                                                 │
                                                  Renders to HTML; sent to browser
                                                                 │
                                                                 ▼
                                                  ┌────────────────────────────┐
                                                  │  HYDRATION                 │
                                                  │  Client components mount,  │
                                                  │  TanStack Query cache      │
                                                  │  pre-seeded from server    │
                                                  └──────────────┬─────────────┘
                                                                 │
                              ┌──────────────────────────────────┼──────────────────────────────────┐
                              │                                  │                                  │
                              ▼                                  ▼                                  ▼
              ┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐
              │ TanStack Query           │    │ WebSocket                │    │ User interaction         │
              │ background refetches     │    │ live updates             │    │ (forms, clicks)          │
              │ on staleTime expiry      │    │ via custom hook          │    │ → mutations              │
              └─────────┬────────────────┘    └─────────┬────────────────┘    └─────────┬────────────────┘
                        │                               │                               │
                        └───────────────┬───────────────┴───────────────────────────────┘
                                        │
                                        ▼
                            React re-renders affected components
```

## 2. Server component initial fetch

```typescript
// app/sites/[slug]/page.tsx (server component)
import { apiServer } from "@/lib/api-client";

export default async function SiteDashboardPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const session = await getServerSession();

  // Authenticated server-side fetches via the OpenAPI-generated SDK
  const [site, snapshot] = await Promise.all([
    apiServer(session).getSite(slug),
    apiServer(session).getDeviceSnapshot(slug, FIRST_DEVICE_ID),
  ]);

  return (
    <DashboardLayout site={site}>
      <PowerHeroTile device_id={site.devices[0].id} initial={snapshot} />
      <VoltagePerPhaseCard device_id={site.devices[0].id} initial={snapshot} />
      {/* ... */}
    </DashboardLayout>
  );
}
```

Key points:
- The page is `async` — Next.js awaits it before sending HTML.
- `apiServer(session)` injects the session's JWT into the request `Authorization` header.
- Initial values are passed as `initial` props to client cards so first paint isn't a skeleton.
- TanStack Query is **pre-seeded** via `dehydrate` / `HydrationBoundary` so the client doesn't refetch the same data immediately on mount.

## 3. Client cards subscribe to TanStack Query + WebSocket

```typescript
// components/dashboard/PowerHeroTile.tsx
"use client";

import { useDeviceLiveStream } from "@/lib/ws-client";
import { useQuery } from "@tanstack/react-query";

export function PowerHeroTile({ device_id, initial }: Props) {
  // TanStack Query holds the canonical "current value" — pre-seeded from server
  const { data } = useQuery({
    queryKey: ["snapshot", device_id],
    queryFn: () => apiClient.getDeviceSnapshot(slug, device_id),
    initialData: initial,
    staleTime: 30_000,
  });

  // WebSocket pushes update the same query.
  // Note: handlers receive the FULL envelope (`{type, data: {...}}`) — fields live
  // under `msg.data`, not at the top level (the dispatcher in §4 unpacks by `msg.type`
  // and forwards the whole envelope, not the inner payload).
  useDeviceLiveStream(device_id, {
    onReading: (msg) => {
      if (msg.data.metric === "active_power_total") {
        queryClient.setQueryData(["snapshot", device_id], (prev) => ({
          ...prev,
          metrics: { ...prev.metrics, active_power_total: msg.data.value },
          snapshot_time: msg.data.time,
        }));
      }
    },
    onSnapshot: (msg) => {
      // The cloud sends the FULL post-merge snapshot state on every snapshot
      // message (per cloud/api-surface.md §5.1) — so a replace is safe.
      queryClient.setQueryData(["snapshot", device_id], msg.data);
    },
  });

  const value = data?.metrics?.active_power_total ?? null;
  // `value` arrives in the catalog unit (kW for power) — the device profile's
  // `scale: 0.001` on power metrics has already converted W → kW upstream
  // (see device-library/acuvim-l-profile.md §3). Don't multiply again here.
  return <Metric value={formatKw(value)} sparkline={...} />;
}
```

The pattern is consistent across cards: TanStack Query owns the cached value; the WebSocket hook merges updates into the cache; React re-renders.

## 4. The WebSocket hook

The hook is a **thin subscriber over a singleton connection pool** keyed by `device_id`. A dashboard with 12 cards subscribing to the same device opens **one** WebSocket connection, not 12 — the acceptance criterion in §8 is built on this.

```typescript
// lib/ws-client.ts
"use client";

// Module-level singleton: one entry per device_id, reference-counted.
type Subscriber = {
  onReading?: (msg: ReadingMessage) => void;
  onSnapshot?: (msg: SnapshotMessage) => void;
  onHeartbeat?: (msg: HeartbeatMessage) => void;
};

type PoolEntry = {
  ws: WebSocket;
  subscribers: Set<Subscriber>;
  refCount: number;
  // Reconnect state, last-known-token, etc.
};

const pool = new Map<string, PoolEntry>();

function acquire(device_id: string, token: string, subscriber: Subscriber): () => void {
  let entry = pool.get(device_id);
  if (!entry) {
    entry = openConnection(device_id, token);
    pool.set(device_id, entry);
  }
  entry.subscribers.add(subscriber);
  entry.refCount += 1;

  return () => {
    entry!.subscribers.delete(subscriber);
    entry!.refCount -= 1;
    if (entry!.refCount === 0) {
      entry!.ws.close();
      pool.delete(device_id);
    }
  };
}

function openConnection(device_id: string, token: string): PoolEntry {
  const url = `${WS_BASE}/sites/${slug}/devices/${device_id}/live`;
  // JWT goes via Sec-WebSocket-Protocol header per cloud/api-surface.md §5.1.
  // Browser WebSocket API repurposes the constructor's `protocols` arg for this.
  const ws = new WebSocket(url, ["solamon-bearer", token]);
  const entry: PoolEntry = { ws, subscribers: new Set(), refCount: 0 };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    for (const sub of entry.subscribers) {
      switch (msg.type) {
        case "reading":   sub.onReading?.(msg);   break;
        case "snapshot":  sub.onSnapshot?.(msg);  break;
        case "heartbeat": sub.onHeartbeat?.(msg); break;
      }
    }
  };

  ws.onclose = (event) => {
    // See §4.1 for close-code semantics + reconnect policy.
    scheduleReconnect(device_id, token, event.code);
  };

  return entry;
}

export function useDeviceLiveStream(device_id: string, handlers: Subscriber) {
  const session = useSession();
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;       // always use latest handlers without re-subscribing

  useEffect(() => {
    if (!session?.accessToken) return;

    // The subscriber forwards into the always-current handlersRef so a re-render
    // with new handler functions does not require a new WS connection.
    const subscriber: Subscriber = {
      onReading:   (m) => handlersRef.current.onReading?.(m),
      onSnapshot:  (m) => handlersRef.current.onSnapshot?.(m),
      onHeartbeat: (m) => handlersRef.current.onHeartbeat?.(m),
    };

    return acquire(device_id, session.accessToken, subscriber);
  }, [device_id, session?.accessToken]);
}
```

### 4.1 Reconnection + close codes

`onclose` triggers a reconnect unless the close was a deliberate teardown (last subscriber unmounted) or an auth failure (close code 1008 — see §4.4). Backoff: 1 s, 2 s, 4 s, 8 s, 16 s, capped at 30 s; reset on successful re-open.

| Close code | Meaning | Reconnect? |
|------------|---------|-----------|
| 1000 | Normal closure (component unmount, last unsubscribe) | No |
| 1006 | Abnormal closure (network drop, broker restart) | Yes — exponential backoff |
| 1008 | Policy violation — JWT invalid / expired | No — trigger session-expiry path (§4.4) |
| 1011 | Server internal error | Yes — exponential backoff |
| 1012 | Service restart | Yes — short backoff (server is rolling) |
| other | Treat as 1006 | Yes — exponential backoff |

Connection state is surfaced via a context (`<ConnectionPill>` in the AppShell renders it).

### 4.4 Token rotation across reconnects

The `useEffect` dependency array is `[device_id, session?.accessToken]`. NextAuth refreshes `session.accessToken` on its own cadence; React re-renders, the `acquire` cleanup runs (decrementing refCount; tearing down the WS only if this was the last subscriber), and a new `acquire` runs with the fresh token. Within a single reconnect cycle the closure already holds the token at the time the WS opened — that's fine because the auth handshake happens at WS open, not on every message. If a reconnect happens *during* a token rotation, the next render closes the stale WS and opens a new one with the fresh token.

A close code of 1008 (auth failure) bypasses the auto-reconnect and instead triggers the session-expiry path (per [`auth.md`](auth.md) §6 step 3): a session refresh check; if the session is genuinely expired, redirect to `/login`.

### 4.2 Sec-WebSocket-Protocol auth

Per [`../cloud/api-surface.md`](../cloud/api-surface.md) §5.1: JWT goes in the `Sec-WebSocket-Protocol` header **only** — the `?token=` query string variant is explicitly disallowed because URLs leak to logs.

The browser's WebSocket API uses the constructor's `protocols` argument for this header:

```typescript
new WebSocket(url, ["solamon-bearer", token]);
```

The first protocol string identifies the auth scheme (server validates it's `solamon-bearer`); the second carries the bearer. The server-side FastAPI WS handler reads the `Sec-WebSocket-Protocol` header, extracts the second value, validates as JWT, and either accepts (echoing `solamon-bearer` back as the negotiated subprotocol per RFC 6455) or rejects (close with code 1008 / "policy violation").

**Log redaction.** The `Sec-WebSocket-Protocol` request header carries the bearer token in plaintext. Caddy's default access-log format captures all request headers — meaning JWTs would land in `/var/log/caddy/access.log`. The Caddyfile MUST redact this header in the `log` block (see [`../infrastructure/caddy-and-dns.md`](../infrastructure/caddy-and-dns.md) §3 — covered there as part of the redaction policy). Treat any backend log retention path as part of the secret's access boundary regardless: even with redaction, FastAPI's own request-logging middleware must skip this header.

### 4.3 Multiple subscribers, one connection

Implemented in §4 above as a module-level singleton pool keyed by `device_id`, with reference counting. Multiple cards on the dashboard subscribe to the same device's live stream and share **one** WebSocket; the connection closes when the last subscriber unmounts. Verified by the §8 acceptance criterion.

## 5. Mutations (control commands)

Issuing a command is a TanStack Query mutation:

```typescript
const issueMutation = useMutation({
  mutationFn: (vars: { window_minutes: number }) =>
    apiClient.postCommand(slug, device_id, {
      logical_metric: "demand_window_minutes",
      type: "set_value",
      parameters: { value: vars.window_minutes },
    }),
  onSuccess: (cmd) => {
    queryClient.setQueryData(["commands", device_id, "live"], cmd);
    // Open the per-command live stream
    setActiveCommandId(cmd.id);
  },
});
```

The 202 response carries the persisted `ControlCommand` (per [`../cloud/control-relay.md`](../cloud/control-relay.md) §3 — `status='sent'` on the happy path, or `'pending'` with `last_publish_error` populated if the broker had transient trouble during the cloud's bounded publish-retry window). The UI inspects status and either:

- Shows the command in the live-status panel and opens `/ws/commands/{id}/live` to track transitions.
- Renders the `last_publish_error` and offers a "Retry" button (which re-issues with the same params; the cloud's background retry might land in the meantime).

The `503 Service Unavailable` path (per [`../cloud/api-surface.md`](../cloud/api-surface.md) §4.4) renders a more prominent error toast: "Cloud broker unreachable; command saved at `pending` and will retry. Check `/sites/{slug}/control` later for status."

## 6. Cross-cutting UX patterns

### 6.1 Stale data indicators

Every live card has an internal `lastUpdate` state. If `Date.now() - lastUpdate > 30_000` the card renders a small "stale" indicator (amber dot + "30s ago" text). The user knows the value isn't current. This is the same behaviour as `<DataFreshness>` in [`components.md`](components.md) §4 — `<DataFreshness>` is the visible component; this paragraph describes the underlying state hook the cards use to drive it.

This works even when the WS is connected but no readings have arrived (e.g., the Pi's Modbus poll is failing; only heartbeats are coming through).

### 6.2 Connection state pill

A small pill in the AppShell's top bar shows the WS connection state:

- **🟢 Connected** — solid green
- **🟡 Reconnecting** — pulsing amber, with the retry-attempt count
- **🔴 Offline** — solid red, after exhausting reconnects

Hover for the last error / next retry timer.

### 6.3 Toast conventions

Three severity levels via `sonner`:

- **success** (green, auto-dismiss after 3 s) — command confirmed, save successful, etc.
- **error** (red, auto-dismiss after 8 s; "View details" button if applicable) — failed mutations, validation errors, network failures
- **info** (neutral, auto-dismiss after 4 s) — informational messages

Don't use `warning` — it ends up overused and the visual impact dilutes. Use `error` or `info`.

### 6.4 Optimistic updates

For control commands, the UI shows the command at `status='pending'` immediately on click — before the server response. On 503, the optimistic state rolls back to "Apply" button enabled with an error toast. On 202, the optimistic state is replaced by the server's authoritative resource.

This avoids the "click-and-wait" pause that feels broken at 200-500 ms request latency.

### 6.5 Loading skeletons

Every page has `loading.tsx` and every card has a built-in skeleton state (when `data === undefined`). Skeletons match the actual layout — same dimensions, same column structure — so the page doesn't shift on hydration.

### 6.6 Error boundaries

`error.tsx` at every route segment. Generic message + "Try again" button + a "Show details" disclosure that reveals the error message (helpful for development; non-disruptive in production where most users wouldn't click it).

## 7. Performance budgets

Bundle measurements are first-load JS for `/sites/{slug}` (the heaviest route) on the production build, gzipped, post-tree-shake. Numbers are **realistic with code-splitting in place** — Tremor + Recharts + shadcn primitives + the Next.js runtime would otherwise blow well past 250 kB on their own.

| Metric | Target | Notes |
|--------|--------|-------|
| First Contentful Paint | < 1 s on a 4 G connection (Lighthouse mobile profile) | Server-rendered HTML reaches browser fast; Tremor hydration is the long-tail |
| Time to Interactive | < 2 s | |
| First-load JS, dashboard route | < 350 kB gzipped | Includes Tremor + Recharts + the WS hook. The 250 kB number from earlier drafts was aspirational; 350 kB is the realistic budget once the chart libraries land. |
| First-load JS, login + admin routes | < 150 kB gzipped | Routes that don't pull in Tremor/Recharts |
| Live render lag | ~50 ms from WS message receipt to React re-render | |
| Memory growth over 1 hour of dashboard view | < 20 MB | No listener / WS / chart-instance leaks |

**Code-splitting is mandatory, not optional**:

- The admin profile detail page (`/admin/profiles/{slug}`) lazy-loads `react-syntax-highlighter` via `next/dynamic`. Next.js's default route-level splitting moves it to a separate chunk; verify with `next build`'s bundle output that the dashboard route doesn't pull it in.
- Recharts is imported once at the chart components — not at the page boundary — so routes without charts don't pay for it.
- Tremor sub-imports use `import { LineChart } from "@tremor/react"` (the package's modern export map is per-component); avoid `import * as Tremor` which defeats tree-shaking.

## 8. Acceptance criteria

- Initial dashboard render shows real numeric values (not placeholders) at first paint when served from the same region as the user (Caddy on EC2 in af-south-1 → SA-based admin laptop is the bench scenario; round-trip < 100 ms). Cross-region or slow-link operation softens to "first values visible within 1 s of nav".
- WebSocket connects within 1 s of mount; first live update visible within the next reading cycle (worst case 10 s).
- Subscribing to the same device from multiple cards opens exactly **one** WebSocket connection (verified via DevTools network tab).
- Killing the network for 60 s, then restoring → reconnect happens within 30 s and the dashboard catches up.
- Issuing a control command shows the optimistic `pending` state within 50 ms of click; transitions through `sent → confirmed` driven by WS messages.
- Bundle sizes stay under budget per route per `next build` output; if Tremor/Recharts grows in a future minor update, lazy-load `<LoadProfileChart>` via `next/dynamic` to keep the initial dashboard chunk under 350 kB.

## 9. Configuration

| Env var | Used by | Example |
|---------|---------|---------|
| `NEXT_PUBLIC_API_BASE` | All HTTP fetches (`apiServer`, `apiClient`, NextAuth Credentials provider) | `https://cloud.solamon.bloemhof.dev` |
| `NEXT_PUBLIC_WS_BASE` | WebSocket connections | `wss://cloud.solamon.bloemhof.dev/api/v1/ws` |
| `NEXTAUTH_SECRET` | NextAuth cookie encryption key (server-only) | 32-byte random hex |
| `NEXTAUTH_URL` | Public origin used by NextAuth callbacks | `https://cloud.solamon.bloemhof.dev` |

`NEXT_PUBLIC_*` env vars are inlined at build time and are visible in client bundles — never put a secret here. The `WS_BASE` and `API_BASE` references throughout this document resolve to these env vars at runtime.

## 10. SDK build pipeline

The TypeScript SDK is regenerated from the cloud's OpenAPI spec on every `npm run build`:

```bash
# package.json scripts:
"prebuild": "openapi-typescript ${API_BASE}/api/v1/openapi.json -o lib/api-schema.ts",
"build": "next build"
```

Local dev: developers run `npm run prebuild` whenever the cloud spec changes (or use `--watch` against a local cloud). CI: pipeline pulls the schema from the cloud's `/openapi.json` once at build start.

The SDK exposes named methods derived from each operation's `operationId` in `openapi.yaml` — operationIds are required for stable method names (e.g., `apiClient.getDeviceSnapshot`); without them `openapi-typescript` falls back to path-derived anonymous functions. See [`../cloud/openapi.yaml`](../cloud/openapi.yaml) — every path declares an explicit `operationId`.

## 11. Cross-references

- [`pages.md`](pages.md) — pages that consume these patterns
- [`components.md`](components.md) — `<ConnectionPill>`, `<DataFreshness>`, `<RelativeTime>`
- [`auth.md`](auth.md) — session token used in WS auth
- [`../cloud/api-surface.md`](../cloud/api-surface.md) §5 — WebSocket contract
- [`../cloud/control-relay.md`](../cloud/control-relay.md) — the state machine the live-stream messages drive
- [`../infrastructure/caddy-and-dns.md`](../infrastructure/caddy-and-dns.md) §3 — `Sec-WebSocket-Protocol` log redaction
