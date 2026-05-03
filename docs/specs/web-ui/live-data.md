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

  // WebSocket pushes update the same query
  useDeviceLiveStream(device_id, {
    onReading: (msg) => {
      if (msg.metric === "active_power_total") {
        queryClient.setQueryData(["snapshot", device_id], (prev) => ({
          ...prev,
          metrics: { ...prev.metrics, active_power_total: msg.value },
          snapshot_time: msg.time,
        }));
      }
    },
    onSnapshot: (msg) => {
      queryClient.setQueryData(["snapshot", device_id], msg.data);
    },
  });

  const value = data?.metrics?.active_power_total ?? null;
  return <Metric value={formatKw(value)} sparkline={...} />;
}
```

The pattern is consistent across cards: TanStack Query owns the cached value; the WebSocket hook merges updates into the cache; React re-renders.

## 4. The WebSocket hook

```typescript
// lib/ws-client.ts
"use client";

export function useDeviceLiveStream(
  device_id: string,
  handlers: {
    onReading?: (msg: ReadingMessage) => void;
    onSnapshot?: (msg: SnapshotMessage) => void;
    onHeartbeat?: (msg: HeartbeatMessage) => void;
  }
) {
  const session = useSession();
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;       // always use latest handlers without re-subscribing

  useEffect(() => {
    if (!session?.token) return;

    const url = `${WS_BASE}/sites/${slug}/devices/${device_id}/live`;

    // JWT goes via Sec-WebSocket-Protocol header per cloud spec §5.1
    // The browser WebSocket constructor's "protocols" arg is repurposed for this.
    const ws = new WebSocket(url, ["solamon-bearer", session.token]);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case "reading":   handlersRef.current.onReading?.(msg);   break;
        case "snapshot":  handlersRef.current.onSnapshot?.(msg);  break;
        case "heartbeat": handlersRef.current.onHeartbeat?.(msg); break;
      }
    };

    ws.onclose = () => {
      // Auto-reconnect with exponential backoff via a wrapper
    };

    return () => ws.close();
  }, [device_id, session?.token]);
}
```

### 4.1 Reconnection

The hook wraps the raw WebSocket in a small reconnect helper that:
- On `onclose` (not initiated by component unmount), waits with exponential backoff (1 s, 2 s, 4 s, 8 s, 16 s, capped at 30 s).
- On reconnect, re-runs the connection setup.
- Surfaces connection state via a context (`<ConnectionPill>` in the AppShell renders it).

### 4.2 Sec-WebSocket-Protocol auth

Per [`../cloud/api-surface.md`](../cloud/api-surface.md) §5.1: JWT goes in the `Sec-WebSocket-Protocol` header **only** — the `?token=` query string variant was removed because URLs leak to logs.

The browser's WebSocket API uses the constructor's `protocols` argument for this header:

```typescript
new WebSocket(url, ["solamon-bearer", token]);
```

The first protocol string identifies the auth scheme (server validates it's `solamon-bearer`); the second carries the bearer. The server-side FastAPI WS handler reads the Sec-WebSocket-Protocol header, extracts the second value, validates as JWT, and either accepts (echoing one of the protocols back) or rejects (close with code 1008 / "policy violation").

### 4.3 Multiple subscribers, one connection

Multiple cards on the dashboard all subscribe to the same device's live stream. The hook implements **subscription multiplexing**: the first call opens the WebSocket and registers the handler; subsequent calls with the same `device_id` reuse the connection and add their handlers. The connection closes when the last subscriber unmounts.

Implementation pattern: a singleton WebSocket pool keyed by `device_id`, with reference counting.

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

The 202 response carries the persisted `ControlCommand` (with `status='sent'` on the happy path or `'pending'` with `last_publish_error` if the broker had transient trouble — see cloud spec §3.4). The UI inspects status and either:

- Shows the command in the live-status panel and opens `/ws/commands/{id}/live` to track transitions.
- Renders the `last_publish_error` and offers a "Retry" button (which re-issues with the same params; the cloud's background retry might land in the meantime).

The `503 Service Unavailable` path renders a more prominent error toast: "Cloud broker unreachable; command saved at `pending` and will retry. Check `/sites/{slug}/control` later for status."

## 6. Cross-cutting UX patterns

### 6.1 Stale data indicators

Every live card has an internal `lastUpdate` state. If `Date.now() - lastUpdate > 30_000` the card renders a small "stale" indicator (amber dot + "30s ago" text). The user knows the value isn't current.

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

| Metric | Target |
|--------|--------|
| First Contentful Paint | < 1 s on a 4 G connection (Lighthouse mobile profile) |
| Time to Interactive | < 2 s |
| Bundle size (initial) | < 250 kB gzipped — Tremor + Recharts + shadcn primitives is the bulk; we accept this in MVP |
| Live render lag | ~50 ms from WS message receipt to React re-render |
| Memory growth over 1 hour of dashboard view | < 20 MB (no listener / WS leaks) |

## 8. Acceptance criteria

- Initial dashboard render shows real numeric values (not placeholders) within 200 ms of nav (server-rendered).
- WebSocket connects within 1 s of mount; first live update visible within the next reading cycle (worst case 10 s).
- Subscribing to the same device from multiple cards opens exactly **one** WebSocket connection (verified via DevTools network tab).
- Killing the network for 60 s, then restoring → reconnect happens within 30 s and the dashboard catches up.
- Issuing a control command shows the optimistic `pending` state within 50 ms of click; transitions through `sent → confirmed` driven by WS messages.
- Bundle size stays under budget; if Tremor + Recharts pushes us over, prune chart imports or switch to bare Recharts for the chart-heavy paths.

## 9. Cross-references

- [`pages.md`](pages.md) — pages that consume these patterns
- [`components.md`](components.md) — `<ConnectionPill>`, `<DataFreshness>`, `<RelativeTime>`
- [`auth.md`](auth.md) — session token used in WS auth
- [`../cloud/api-surface.md`](../cloud/api-surface.md) §5 — WebSocket contract
- [`../cloud/control-relay.md`](../cloud/control-relay.md) — the state machine the live-stream messages drive
