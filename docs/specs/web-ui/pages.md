# Web UI — page inventory

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)

Per-route contracts: purpose, auth requirement, data dependencies, live subscriptions, layout, acceptance.

Cross-references:
- API endpoints from [`../cloud/api-surface.md`](../cloud/api-surface.md)
- Card layouts from [`../../../requirements/acuvim_mvp_register_scope.md`](../../../requirements/acuvim_mvp_register_scope.md) §J (the canonical dashboard layout)
- Live-data plumbing from [`live-data.md`](live-data.md)

---

## 1. Route map

```
/login                                        public
/                                             auth required → redirect to /sites/{first-slug}
/sites/{slug}                                 LOAD ASSESSMENT DASHBOARD (primary view)
/sites/{slug}/control                         CONTROL PANEL (demand window flip + audit list)
/sites/{slug}/devices/{device_id}             Device detail (deeper view)
/admin                                        Admin landing → redirect to /admin/profiles
/admin/profiles                               Read-only profile browser (editor = SOL-12)
/admin/profiles/{profile_slug}                Profile detail (read-only)
/admin/sites                                  Site list + setup info
/admin/users                                  User list (MVP: just admin)
```

All `/admin/*` routes require `role = admin` (the only operator role in MVP).

## 2. App shell

A common layout wraps every page (except `/login`):

- **Top bar:** project logo, current site selector (links to other sites — only one site in MVP), user menu (display name, logout)
- **Side nav:** "Dashboard" / "Control" / "Devices" / "Admin"
- **Content area:** the page itself
- **Toast region:** ephemeral notifications (success / error / info)
- **Footer:** version + git SHA (from build env)

Implemented as a shared `AppShell` server component in `app/layout.tsx`. Per-page `loading.tsx` files render skeletons during transitions; `error.tsx` files render error boundaries.

---

## 3. `/login`

**Auth:** public.

**Purpose:** authenticate the operator; redirect to `/`.

**Data dependencies:**
- `POST /api/v1/auth/login` (NextAuth's Credentials provider calls this)

**Layout:**

```
┌──────────────────────────────────────────────────┐
│         Solar Monitor                              │
│                                                    │
│         ┌──────────────────────────┐               │
│         │ Email / Password         │               │
│         │ [           email      ] │               │
│         │ [          password    ] │               │
│         │ [       Sign In        ] │               │
│         └──────────────────────────┘               │
│                                                    │
│         (no signup link — invite-only)            │
│                                                    │
└──────────────────────────────────────────────────┘
```

**Behaviour:**
- React Hook Form + Zod validates the form (email format, password non-empty) before submit.
- On submit: NextAuth's `signIn("credentials", { email, password, redirect: false })`.
- Success: redirect to the URL in `?callbackUrl=` if present, else `/`.
- Failure: stay on page, show toast "Email or password incorrect" (don't disclose which).
- Form disables during submit; spinner on the Submit button.

**Acceptance:**
- Wrong credentials → toast appears, no redirect, focus returns to email field.
- Correct credentials → redirect within 500 ms; subsequent navigation has the session cookie set.
- Hitting `/login` while already logged in → redirect to `/`.

---

## 4. `/` — landing redirect

**Auth:** required.

**Purpose:** redirect-only route. Server component reads the session, fetches the user's accessible sites via `GET /api/v1/sites`, redirects to `/sites/{first-slug}`.

**Behaviour:**
- If the user has no sites: render a placeholder "No sites assigned to your account" with a logout link.
- If the user has 1+ sites (MVP: always 1): redirect to `/sites/{first-slug}`.

---

## 5. `/sites/{slug}` — Load Assessment Dashboard

**Auth:** required. User must have `view` access to the site.

**Purpose:** the primary operator view. Renders live telemetry as cards + the main load-profile chart.

**Data dependencies:**
- `GET /api/v1/sites/{slug}` — site metadata + devices list + health (server-side initial fetch)
- `GET /api/v1/sites/{slug}/devices/{device_id}/snapshot` — initial values for all metrics (server-side initial fetch)
- `GET /api/v1/sites/{slug}/devices/{device_id}/readings?metric=active_power_total&from=...&to=...` — initial chart data (client-side via TanStack Query)
- `GET /api/v1/metrics-catalog` — for label / unit lookups (cached in client; rarely changes)

**Live subscriptions:**
- `WS /api/v1/ws/sites/{slug}/devices/{device_id}/live` — server forwards MQTT telemetry as `reading` / `snapshot` / `heartbeat` messages.

**Layout:** see [`../../../requirements/acuvim_mvp_register_scope.md`](../../../requirements/acuvim_mvp_register_scope.md) §J for the full card map. Summary:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  HERO ROW (3 cols)                                                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                         │
│  │ Active power │ │ Energy today │ │ Demand       │                         │
│  └──────────────┘ └──────────────┘ └──────────────┘                         │
├────────────────────────────────────────────────────────────────────────────┤
│  PER-PHASE ROW (4 cols)                                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐ ┌──────────────────────┐          │
│  │ Voltages│ │ Currents│ │ Per-phase P │ │ Power factor (4 tiles)│         │
│  └─────────┘ └─────────┘ └─────────────┘ └──────────────────────┘          │
├────────────────────────────────────────────────────────────────────────────┤
│  POWER QUALITY ROW (5 cols)                                                │
│  ┌────────┐ ┌────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────┐            │
│  │V-unbal.│ │I-unbal.│ │ Freq    │ │ THD     │ │ Edge health  │            │
│  └────────┘ └────────┘ └─────────┘ └─────────┘ └──────────────┘            │
├────────────────────────────────────────────────────────────────────────────┤
│  MAIN CHART                                                                 │
│  Psum over time · window selector · overlay toggles                        │
├────────────────────────────────────────────────────────────────────────────┤
│  COLLAPSIBLE SIDEBAR — SITE SETUP (shadcn <Sheet>)                          │
│  PT/CT ratios · wiring type · demand window · sub_variant · last config   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Render strategy:**
- The page route (`app/sites/[slug]/page.tsx`) is a **server component**. It does the initial `GET /sites/{slug}` and `/snapshot` fetches and renders the cards with their initial values.
- Each card is a **client component** (`"use client"`) that subscribes to the WS via the `useDeviceLiveStream` hook and re-renders on incoming messages.
- The main chart's data is fetched client-side via TanStack Query (the time-window query is interactive; better to keep it on the client).

**Acceptance:**
- First paint shows real values within 200 ms of navigation (server-rendered).
- WS connects within 1 s of mount; values update at the cadence of incoming readings.
- Window selector on the main chart triggers a refetch; loading skeleton appears during the request.
- WS drop: cards show a "stale" indicator after 30 s of no updates; auto-reconnect within 5 s of network recovery.

---

## 6. `/sites/{slug}/control` — Control Panel

**Auth:** required. User must have `operate` access to the site.

**Purpose:** issue control commands; show live status + audit list.

**Data dependencies:**
- `GET /api/v1/sites/{slug}/devices/{device_id}/snapshot` — current value of `demand_window_minutes` (server-side initial)
- `GET /api/v1/sites/{slug}/devices/{device_id}/commands?limit=20` — recent command history (server-side initial)
- `POST /api/v1/sites/{slug}/devices/{device_id}/commands` — issue a new command (client mutation)

**Live subscriptions:**
- `WS /api/v1/ws/commands/{id}/live` — opened only after a command is issued; receives the `current` snapshot then `transition` messages until the command reaches a terminal state, then auto-closes.

**Layout:**

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Demand Integration Window                                               │
│  Currently: 15 min  [▼ dropdown: 1 / 5 / 10 / 15 / 30]   [Apply]        │
│                                                                          │
│  Live status of last command:                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ cmd-uuid · type=set_demand_window · window=30                    │    │
│  │ ✓ Issued    14:32:01                                             │    │
│  │ ✓ Sent      14:32:02                                             │    │
│  │ ⏳ Awaiting confirmation...                                       │    │
│  │ ✓ Confirmed (read-back: 30 min)  14:32:03                        │    │
│  └──────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────┤
│  Last 20 commands (table, paginated)                                     │
│  Time          User    Type                Param   Status   Read-back   │
│  14:32         Marius  set_demand_window   30      ✓        30          │
│  14:15         Marius  set_demand_window   15      ✓        15          │
│  ...                                                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Behaviour:**
- The dropdown is constrained by the device's active profile's `control.demand_window_minutes.allowed_values` (fetched at page load).
- "Apply" triggers `POST /commands`. Optimistic update: the live-status panel renders `pending` / `sent` from the response immediately.
- WS connection opens with the returned command id; pushes drive the live-status panel through `pending → sent → confirmed/failed/expired`.
- On `confirmed`: refresh the snapshot (the new value is now reflected in the main dashboard's Site Setup sidebar) and the command history.
- On `failed`: render the error_message under the live-status panel; toast appears.
- Race condition handling: if the operator clicks Apply while a previous command is still pending, disable the button until the WS receives a terminal state.

**Acceptance:**
- Issued command appears in live-status within 100 ms of the 202 response.
- Status transitions render within 200 ms of WS message arrival.
- Audit table appends the new command after terminal state.
- Authorisation check: a `view`-only user gets 403 from the POST and the form shows "Insufficient permission" rather than crashing.
- Operator can use the panel from a phone (responsive Tailwind).

---

## 7. `/sites/{slug}/devices/{device_id}` — Device Detail

**Auth:** required. View permission.

**Purpose:** deeper diagnostic view than the dashboard. Per-metric history, raw values, full block readability, last fingerprint identifiers.

**Data dependencies:**
- `GET /api/v1/sites/{slug}/devices/{device_id}` — device detail
- `GET /api/v1/sites/{slug}/devices/{device_id}/readings?metric=...` — per-metric history queries (lazy on tab change)
- `GET /api/v1/sites/{slug}/devices/{device_id}/commands` — command history
- `GET /api/v1/device-profiles/{profile_slug}` — profile detail for the cross-reference

**Live subscriptions:** same WS as `/sites/{slug}` — shared connection.

**Layout:** tabbed interface:
- **Overview** — current state (snapshot table, fingerprint identifiers if populated, sub-variant note)
- **Telemetry** — per-metric mini-charts in a grid; click a chart to expand
- **Commands** — full audit list (paginated, filterable)
- **Profile** — read-only view of the active device profile (with hex addresses)

**Acceptance:**
- All four tabs render within 500 ms of nav.
- Metric grid renders 30+ mini-charts without performance issues (Tremor handles it; if not, virtualise via `react-window`).

---

## 8. `/admin/profiles`

**Auth:** required. Admin role.

**Purpose:** browse loaded device profiles. Read-only — full editor is [SOL-12](https://linear.app/solamon/issue/SOL-12).

**Data dependencies:**
- `GET /api/v1/device-profiles` — list

**Layout:** simple table; click row → `/admin/profiles/{slug}`.

## 9. `/admin/profiles/{profile_slug}`

**Auth:** required. Admin role.

**Purpose:** profile detail. Renders the YAML in a read-only `<pre>` with syntax highlighting (using `react-syntax-highlighter` or similar). Hex addresses rendered as hex (not the integer JSONB representation — render-time conversion).

**Data dependencies:**
- `GET /api/v1/device-profiles/{profile_slug}` — full profile JSON

## 10. `/admin/sites`

**Auth:** required. Admin role.

**Purpose:** list of sites with health summary, link to each site's dashboard.

**Layout:** table — slug / name / timezone / last_seen_at / status pill / device count.

## 11. `/admin/users`

**Auth:** required. Admin role.

**Purpose:** read-only user list. MVP shows just the admin user; multi-user RBAC is post-MVP.

**Layout:** simple table — email / display_name / tier / role / last_login.

---

## 12. Cross-cutting page concerns

### 12.1 Loading states

Every page has a `loading.tsx` rendering a skeleton matching the page layout. Tremor cards render with skeleton placeholders; the main chart shows a shimmer. Don't ever show a fully blank page during navigation.

### 12.2 Error boundaries

Every page has an `error.tsx` rendering a friendly error card with:
- Short message ("Couldn't load this site")
- A "Try again" button (calls `reset()` from the Next.js error boundary)
- A details accordion showing the error message + a "Copy details" button (for support)

### 12.3 Empty states

`/admin/sites` with 0 sites, `/admin/users` with 1 user, `/sites/{slug}/commands` with 0 commands — each has a copy + illustration: "No commands issued yet. Use the Control panel to issue one."

### 12.4 Accessibility

- All interactive elements keyboard-navigable.
- Form labels associated with inputs.
- Toast region uses ARIA live regions.
- Charts have a "View as table" alternate (Tremor provides this; ensure it's enabled).
- Colour-coded data (red/yellow/green for unbalance, etc.) also uses non-colour cues (icons, position, text).

### 12.5 Browser support

Modern evergreen browsers: latest Chrome, Edge, Firefox, Safari. No IE11. Browser WebSocket and Fetch APIs used directly.

---

## 13. Cross-references

- [`components.md`](components.md) — what the cards / charts / layouts are made of
- [`live-data.md`](live-data.md) — RSC + TanStack Query + WebSocket plumbing
- [`auth.md`](auth.md) — login flow + session + route protection
- [`../cloud/api-surface.md`](../cloud/api-surface.md) — every endpoint these pages consume
- [`../cloud/control-relay.md`](../cloud/control-relay.md) — the control state machine the panel renders
