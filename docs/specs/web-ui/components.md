# Web UI — components

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)

Component inventory. The MVP UI is built from three layers stacked from low to high:

1. **shadcn/ui primitives** — accessible, unstyled-by-default React components (Button, Card, Dialog, etc.) copy-pasted into the repo.
2. **Tremor** — analytics-dashboard-specific components (Metric, LineChart, BarList, Donut) layered on Recharts.
3. **Solamon custom cards** — domain-specific compositions of the above (PowerHeroTile, VoltagePerPhaseCard, etc.).

---

## 1. shadcn/ui — primitives

shadcn/ui works by you copying source code into your repo (`components/ui/*.tsx`). No npm dep on the components themselves — only on `@radix-ui/*` (which the shadcn pieces wrap) and `class-variance-authority` / `clsx` / `tailwind-merge`.

Components installed for MVP (run `npx shadcn add <name>` for each):

| Component | Used in |
|-----------|---------|
| `button` | Forms, control panel, everywhere |
| `card` | Most cards (the wrapper, not the contents) |
| `input` | Login, command forms |
| `label` | Form fields |
| `select` | Demand window dropdown, time-window selector |
| `form` | Login form (RHF integration) |
| `dialog` | Confirm-action prompts (e.g., "really apply this command?") |
| `sheet` | Site Setup sidebar on the dashboard |
| `dropdown-menu` | User menu in the top bar |
| `toast` (sonner) | Ephemeral notifications |
| `table` | Audit lists, profile tables, admin lists |
| `tabs` | Device detail page |
| `skeleton` | Loading placeholders |
| `tooltip` | Hover hints on cards |
| `badge` | Status pills (online / offline / fault) |
| `separator` | Section dividers |

Installing shadcn primitives from the CLI overwrites a path under `components/ui/`. Treat as your code thereafter — diff and review before regen.

## 2. Tremor — dashboard widgets

Tremor 3.x components used:

| Component | Used in |
|-----------|---------|
| `<Card>` | Tremor's card variant (richer than shadcn's; used inside dashboard cards) |
| `<Metric>` | Big-number displays (Active power, Energy today) |
| `<Title>` / `<Subtitle>` / `<Text>` | Card headings and sublabels |
| `<LineChart>` | Main load-profile chart on the dashboard |
| `<SparkLineChart>` | 60-second sparkline under hero metrics |
| `<BarList>` | Per-phase power bars |
| `<DonutChart>` | (Reserved for future — energy breakdown) |
| `<ProgressBar>` | Voltage range "in band" indicator |
| `<Badge>` | Trend / delta indicators |

Tremor charts use Recharts under the hood — when Tremor's API is too restrictive (e.g., custom tooltip rendering, nonstandard axis configuration) we drop down to bare `recharts` directly. `recharts` is already a transitive dep of Tremor.

## 3. Solamon custom dashboard cards

Custom React components composing shadcn + Tremor + raw Tailwind. Live in `components/dashboard/*.tsx`.

| Component | Props | What it renders |
|-----------|-------|-----------------|
| `<PowerHeroTile>` | `{ device_id }` | Total active power as a `<Metric>` + 60-second `<SparkLineChart>`. Subscribes to `useDeviceLiveStream`. |
| `<EnergyTodayTile>` | `{ device_id }` | kWh import / export with Δ-vs-yesterday under each. |
| `<DemandTile>` | `{ device_id }` | Current `active_power_demand` + peak with timestamp. Click to navigate to `/sites/{slug}/control`. |
| `<VoltagePerPhaseCard>` | `{ device_id }` | Three numeric tiles (V_a / V_b / V_c) with a `<ProgressBar>` showing position within the 207-253 V healthy band. Per-tile colour: green in band, amber 5 % outside, red 10 % outside. |
| `<CurrentPerPhaseCard>` | `{ device_id }` | Three bars + a fourth thin bar for neutral current. Bars relative to max-current-in-period. |
| `<PerPhasePowerCard>` | `{ device_id }` | Three bars (P_a / P_b / P_c) showing balance. |
| `<PowerFactorCard>` | `{ device_id }` | Four numeric tiles (PF_a / PF_b / PF_c / PF_sum). **Sign-aware rendering**: each tile shows the sign explicitly (e.g., `+0.92`). Mixed signs across phases are highlighted with a warning border and a tooltip "Mixed PF signs across phases — check load characteristics or CT polarity. Confirm with per-phase active power signs (a CT-flipped phase typically shows negative `active_power_l{n}` on a load-only site)." Don't label this purely as a CT-flip diagnostic — heavily reactive single-phase loads (a motor with capacitor bank on one phase) can produce mixed-sign PF without any CT issue. |
| `<UnbalanceCard>` | `{ device_id, kind: "voltage" \| "current" }` | Numeric value + 24-hour `<SparkLineChart>` of the unbalance. Threshold lines drawn at 2 % and 5 %. |
| `<FrequencyCard>` | `{ device_id }` | Big-number `<Metric>` centered on 50.0 Hz target with min/max-last-hour underneath. (Tremor doesn't have a circular gauge in 3.x — for MVP we render the numeric "+/- delta from 50 Hz" with colour, not a literal gauge.) |
| `<ThdCard>` | `{ device_id }` | Two rows of three small bars: THD V on top, THD I on bottom. Threshold lines at 5 % (V) and a context-dependent reference for I. |
| `<EdgeHealthCard>` | `{ site_slug }` | Modbus errors / minute, last successful read (relative time), Pi heartbeat (relative time), buffer depth in seconds, halted blocks if any (rendered from the heartbeat payload's `halted_blocks: string[]` field — see [`../cloud/mqtt-contracts.md`](../cloud/mqtt-contracts.md) §5.1). Subscribes to the `heartbeat` WS message type. |
| `<LoadProfileChart>` | `{ device_id }` | The big main chart. `<LineChart>` with selectable window (1 h / 6 h / 24 h / 7 d) and overlay toggles (Pa/b/c, Q, S, PF). Click + drag to zoom. Demand peaks marked with vertical lines. |
| `<SiteSetupSheet>` | `{ device_id }` | shadcn `<Sheet>` (right-side drawer) showing PT/CT ratios, wiring type, demand window setting (with link to Control panel), sub-variant note, last config-read time. |
| `<CommandStatusTimeline>` | `{ command_id }` | Vertical timeline with per-state rows (pending / sent / confirmed / failed / expired). Subscribes to `useCommandLiveStream`. Each row has timestamp + checkmark / spinner / X. Auto-disconnects WS on terminal state. |
| `<CommandHistoryTable>` | `{ device_id, limit }` | shadcn `<Table>` of recent commands. |

Each custom card knows its own `device_id` (or `site_slug`); doesn't lift state up to the page. Pages compose them and provide the IDs.

## 4. Auxiliary components

| Component | Purpose |
|-----------|---------|
| `<AppShell>` | Top bar + side nav + footer. Server component. |
| `<UserMenu>` | Display name, sign-out. Client component (uses session). |
| `<SiteSelector>` | Dropdown for site switching. **MVP behaviour:** the dropdown is rendered disabled and shows the single site's name (no other sites to switch to). When multi-site lands post-MVP, the same component flips to active and links to other sites. (`pages.md §2`'s "links to other sites" describes the eventual behaviour, not MVP.) |
| `<RelativeTime>` | "5s ago" / "2 min ago" / "1 hour ago" auto-updating client component. **All instances share a single broadcast tick** (one `setInterval(1000)` at the React tree root, registered via a `RelativeTimeTickContext`); per-instance timers are forbidden because the dashboard renders 30+ instances and per-instance churn is wasteful. Components subscribe to the context, recompute their own label on each tick, and bail out of re-render when the rounded label hasn't changed. |
| `<ConnectionPill>` | Tiny pill in the top bar showing live-WS connection state (connected / reconnecting / offline). |
| `<DataFreshness>` | "Last update: 3s ago" indicator on dashboard cards; turns amber if last update is more than 30 s old. Underlying state hook described in [`live-data.md`](live-data.md) §6.1. |
| `<DemoFixturesBadge>` | Visible top-bar badge rendered only when `NEXT_PUBLIC_DEMO_FIXTURES=true`. Hover/focus text explains that current values are fixture/replay data. Never appears in production mode. |
| `<FirstTelemetryChecklist>` | Full-width fresh-site panel showing Pi heartbeat, MQTT connection, device configuration, Modbus reachability, and first snapshot status. Used before the dashboard has real metrics. |
| `<HexAddressBadge>` | Renders a Modbus register address as `0x0600` in a monospaced badge. Used in the Profile detail page. Renderer is responsible for the integer→hex conversion; only specific *address fields* (see [`pages.md`](pages.md) §9 for the allowlist) are rendered as hex, NOT every integer in the profile. |
| `<LoadMoreButton>` | Cursor-paginated "Load more" trigger for any table backed by a cursor API (commands history, audit log, devices list). Replaces a page-numbered pager — the cloud's pagination is `?cursor=<opaque>` per `../cloud/api-surface.md §4` and has no concept of "page 5 of 12". On click: re-fetches with `?cursor=<next_cursor>`; appends the new page to the existing list; hides the button when `next_cursor` is null. |

## 5. Design tokens

Tailwind config (`tailwind.config.ts`) extends the default with:

```ts
{
  theme: {
    extend: {
      colors: {
        // Solamon brand neutrals + status colours.
        // Deliberately limited palette — the dashboard's job is to show NUMBERS,
        // not look pretty. Heavy chrome obscures the data.
        brand: {
          50:  "#f7f9ff",
          900: "#0a1f44",
        },
        ok:    "#10b981",   // green — within healthy band
        warn:  "#f59e0b",   // amber — out of band but not critical
        crit:  "#ef4444",   // red — critical / fault
        muted: "#9ca3af",   // grey — stale / unknown
      },
      fontFamily: {
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],   // for hex addresses, raw values
      },
    },
  },
}
```

**Status colour rule:** `ok` / `warn` / `crit` / `muted` are the only status colours. Don't introduce new ones for new card types — pick one of these.

**Status-pill mapping** (the `badge` component renders one of five values from `app.device.status`):

| `status` | Colour token | Notes |
|----------|-------------|-------|
| `online` | `ok` | Heartbeat fresh + recent telemetry |
| `fault` | `crit` | Device reports active fault |
| `unreachable` | `warn` | Heartbeat fresh but device unreachable from Pi (Modbus errors) |
| `offline` | `muted` | No heartbeat for > 5 min, OR LWT received |
| `unknown` | `muted` | Initial state before first heartbeat / never seen |

**Enum / categorical metric rendering.** Some logical metrics carry integer codes that the catalog maps to symbolic names (e.g., `current_wiring_type`: `{0: "3CT", 1: "2CT", 2: "1CT"}`). The cloud snapshot endpoint resolves enum metrics to their **string symbolic form** before serving — so the snapshot returns `metrics: { current_wiring_type: "3CT" }`, not `0`. Confirmed in [`../cloud/api-surface.md`](../cloud/api-surface.md) §4.5 (`DeviceSnapshot.metrics`). Web-ui components render the string directly; no client-side `enum_values` lookup needed. The `app.logical_metric.enum_values` JSONB map is only used inside the cloud's ingestion path and on the admin profile-detail page (which fetches the raw catalog).

**Numeric typography:** all values are tabular-nums (`font-variant-numeric: tabular-nums`) so digits don't shift width as values change. Tailwind's `font-tabular-nums` utility.

**Data density:** information-dense by default. Operators want every relevant number on screen at once; we don't enforce 24-px line heights and acres of whitespace.

**Missing-value rendering:** no dashboard component may coerce `null`, `undefined`, `NaN`, or missing metric keys to `0`. Render a muted dash plus `Unavailable`, keep the last good value if one exists and mark it stale, or show the metric quality state (`uncertain` / `bad`) when the cloud supplies it. This prevents the POC from accidentally presenting "no telemetry" as "zero load".

**Stable live layout:** cards reserve fixed space for their primary number, unit, sparkline, freshness label, and status badge. A live update must not change card height or push neighbouring cards around.

## 6. Conventions

### 6.1 Server vs client components

Default to server components. Add `"use client"` only when:
- The component subscribes to WebSocket data (`useDeviceLiveStream`, `useCommandLiveStream`)
- The component uses `useState` / `useEffect` / TanStack Query
- The component handles user interaction (forms, dropdowns)

Pages are server components; cards are typically client components (because they live-update); the chart is a client component.

### 6.2 File structure

```
app/
  layout.tsx                             # AppShell
  loading.tsx
  error.tsx
  page.tsx                               # / (redirect)
  login/
    page.tsx                             # /login
    layout.tsx                           # no AppShell on login
  sites/[slug]/
    page.tsx                             # /sites/{slug}
    loading.tsx
    error.tsx
    control/page.tsx                     # /sites/{slug}/control
    devices/[device_id]/page.tsx
  admin/...

components/
  ui/                                    # shadcn primitives
  dashboard/                             # custom cards (§3)
  AppShell.tsx
  UserMenu.tsx
  ...

lib/
  api-client.ts                          # wraps the OpenAPI-generated SDK with auth
  ws-client.ts                           # useDeviceLiveStream + useCommandLiveStream
  query-client.ts                        # TanStack QueryClient + Provider
  zod-schemas.ts                         # form validation schemas

styles/
  globals.css                            # Tailwind directives + a few base overrides
```

### 6.3 Imports

Absolute imports via `@/` alias mapped to repo root in `tsconfig.json`. e.g., `import { Button } from "@/components/ui/button"`.

### 6.4 Testing (deferred to implementation phase)

Component-level testing planned via Vitest + React Testing Library; not specified in this MVP — implementation-phase concern. Visual regression via Playwright is post-MVP.

## 7. Cross-references

- [`pages.md`](pages.md) — which page uses which component
- [`live-data.md`](live-data.md) — `useDeviceLiveStream` and `useCommandLiveStream` hook contracts
- [`auth.md`](auth.md) — `<UserMenu>` and protected-route behaviour
- [`demo-readiness.md`](demo-readiness.md) — fixture badge, first telemetry checklist, presentation polish
