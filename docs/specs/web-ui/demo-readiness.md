# Web UI — POC demo readiness

**Spec group:** [web-ui](README.md)
**Linear:** [SOL-9](https://linear.app/solamon/issue/SOL-9)

The MVP is a POC, but the first audience is a real prospective client. The UI must feel like a trustworthy operations tool: live, specific, and calm under imperfect bench conditions.

---

## 1. Demo goal

The demo story is:

1. Johan logs in.
2. The dashboard opens directly on the bench/prospect site.
3. Current load, demand, energy, phase balance, power quality, and edge health are visible without explanation.
4. Johan changes the Acuvim demand integration window.
5. The control timeline shows the command moving through cloud, edge, Modbus write, and read-back confirmation.
6. If a cable, LTE link, broker, or meter is offline, the UI explains what is missing and what to check.

The UI should impress by showing operational competence, not decorative flourish. Numbers, freshness, and provenance are the hero.

## 2. Demo mode

The application supports a local-only demo fixture mode for UI development and rehearsals:

| Item | Requirement |
|------|-------------|
| Env flag | `NEXT_PUBLIC_DEMO_FIXTURES=true` enables fixture-backed pages. Default is unset/false. |
| Scope | Local dev and rehearsal only. Production Docker images must ship with the flag unset. |
| Label | Every fixture-backed page renders a visible `Demo fixtures` badge in the top bar. |
| Data source | Static JSON fixtures under `packages/web_ui/tests/fixtures/`, shaped exactly like the OpenAPI responses and WebSocket envelopes. |
| WebSocket simulation | The fixture adapter replays readings at realistic cadences: power every 10 s, demand every 30 s, energy/THD every 60 s, heartbeat every 60 s. |
| Safety | Fixture mode never calls `POST /commands`; the control panel simulates the command timeline and labels it `simulated`. |

This is not a fake production path. It exists so the UI can be rehearsed while the bench hardware or cloud stack is unavailable, and so visual regressions can be caught deterministically.

## 3. Live-data confidence

Every dashboard card that shows a live value also shows enough context for an operator to trust it:

- value and unit, using the catalog unit;
- last update age via `<DataFreshness>`;
- quality state when available (`good`, `uncertain`, `bad`);
- stale state after 30 s without a relevant reading;
- unavailable state when the metric has never arrived.

No card silently renders `0` for missing data. Missing, stale, and real zero are three different UI states.

## 4. First-run experience

A freshly bootstrapped site often has auth and site metadata before telemetry. The dashboard must still feel deliberate:

- The page header renders site name, slug, connection state, and device identity.
- A full-width "Waiting for first telemetry" panel shows the expected first-message window and the next checks: Pi heartbeat, MQTT broker, Modbus TCP address, Acuvim power.
- The `EdgeHealthCard` renders even before device readings arrive, because heartbeat may be the first useful signal.
- As soon as the first `snapshot` WebSocket message arrives, the page transitions into the normal dashboard without a hard refresh.

## 5. Presentation polish

These are acceptance-level UI constraints for the POC:

- The first viewport of `/sites/{slug}` contains the site name, live connection pill, active power, energy today, demand, and at least one power-quality signal on a 1440 px wide display.
- The dashboard uses a dense 12-column grid on desktop and a single-column stack on narrow screens; no nested cards.
- Status colour is limited to the tokens in [`components.md`](components.md) §5. Do not invent a separate demo palette.
- Numeric values use tabular digits and stable card dimensions, so live updates do not shift the layout.
- A footer or top-bar build label shows version/git SHA so screenshots are traceable.
- Error and empty states look intentionally designed; no raw JSON or stack traces are visible unless the operator opens a details disclosure.

## 6. Rehearsal checklist

Before a client-facing demo, capture the following evidence:

| Evidence | Acceptance |
|----------|------------|
| Login screenshot | `/login` renders cleanly; wrong password path shows the expected toast. |
| Dashboard screenshot | Real or fixture values fill the hero row; connection state is visible. |
| Live update recording | At least one card updates from a WebSocket message without a page refresh. |
| Control recording | Demand-window command reaches `confirmed`, or fixture mode clearly labels the simulated timeline. |
| Offline screenshot | Network/broker/meter failure produces a useful operator-facing state, not a crash. |
| Mobile screenshot | `/sites/{slug}` and `/sites/{slug}/control` are usable at 390 px width. |

## 7. Non-goals

- No marketing landing page.
- No client portal in MVP.
- No white-label theme work.
- No hidden synthetic values in production mode.
- No complex animation beyond small loading, reconnecting, and command-progress affordances.

## 8. Cross-references

- [`pages.md`](pages.md) — route-level first-run and demo acceptance.
- [`components.md`](components.md) — live cards, status tokens, AppShell, freshness.
- [`live-data.md`](live-data.md) — fixture mode and WebSocket replay behaviour.
- [`auth.md`](auth.md) — login and session expiry paths.
