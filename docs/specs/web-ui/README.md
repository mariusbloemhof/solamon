# Web UI — detail specs

**Spec group owner:** [SOL-9 — MVP — Web UI](https://linear.app/solamon/issue/SOL-9)
**Parent design doc:** [`docs/specs/2026-05-02-mvp-design.md`](../2026-05-02-mvp-design.md) §9
**Status:** Working spec.

---

## What this spec group covers

The Next.js + React + Tailwind web application — operator-facing dashboards, control panel, and admin browse views. Single-page-app feel (App Router with client transitions) but server-rendered first paint via React Server Components.

Audience: **Marius and Johan** (operations users) in MVP. Client-tier (read-only customer view) is post-MVP.

## Files in this folder

| File | What it specifies |
|------|-------------------|
| [`README.md`](README.md) | This index. |
| [`pages.md`](pages.md) | Page inventory — every route, its purpose, auth requirement, data dependencies, live subscriptions, layout. |
| [`components.md`](components.md) | Component inventory — shadcn/ui primitives, Tremor charts, custom dashboard cards, design tokens. |
| [`live-data.md`](live-data.md) | RSC + TanStack Query + WebSocket flow — initial render, hydration, live updates, optimistic mutations, reconnection, error handling. |
| [`auth.md`](auth.md) | Login UX, NextAuth credentials provider, session management, route protection middleware, logout. |

## Stack summary (recap of main spec §9.1)

| Concern | Choice |
|---------|--------|
| Framework | **Next.js 15** (App Router, React Server Components) |
| Styling | **Tailwind 4.x** |
| Component primitives | **shadcn/ui** — copy-paste components, no version lock-in |
| Charts & cards | **Tremor** (primary, layered on Recharts); bare Recharts where Tremor's API is too restrictive |
| Client state | **TanStack Query** — server data caching, mutations, invalidation |
| Live data | **Native browser WebSocket** wrapped in a small custom hook; no external lib |
| Forms | **React Hook Form** + **Zod** |
| API client | Auto-generated TypeScript SDK from FastAPI's `/api/v1/openapi.json` (via `openapi-typescript`) |
| Auth | **NextAuth (Auth.js v5)** Credentials provider → FastAPI `/api/v1/auth/login` |
| Bundling | Next.js's built-in (Turbopack in dev, webpack in prod) |
| Hosting (MVP) | Same EC2 box, served behind Caddy, alongside FastAPI |
| Hosting (post-MVP) | Vercel / AWS Amplify / S3+CloudFront — first-class portable target |

## Acceptance for SOL-9

- All five sub-specs in this folder committed and internally consistent.
- The page inventory in [`pages.md`](pages.md) matches main spec §9.2 (no drift).
- Live-data flow in [`live-data.md`](live-data.md) consumes the WebSocket envelopes documented in [`../cloud/api-surface.md`](../cloud/api-surface.md) §5.
- Auth flow in [`auth.md`](auth.md) consumes the endpoints documented in [`../cloud/api-surface.md`](../cloud/api-surface.md) §3.
- Bench Day 6 deliverable: `/login` works; `/sites/{slug}` renders an empty layout with placeholder cards.
- Bench Day 7-8 deliverable: dashboard cards render real data from the bench Acuvim.
- Bench Day 9-10 deliverable: control panel issues commands; live state machine renders correctly.

## Out of MVP scope

- Client portal (Tier 2 user model — operator-only in MVP)
- White-labelling / theming / dark mode toggle
- Multi-site selector beyond redirect-to-first
- Per-user RBAC UI
- Profile editor → [SOL-12](https://linear.app/solamon/issue/SOL-12)
- Full audit-log browser → arrives with audit-browser UI work
- Mobile-specific layouts (responsive Tailwind covers phone-rendering at "scale down" quality)
- i18n / l10n
- Push notifications / WebPush for alerts
