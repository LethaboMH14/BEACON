# Ops console mockups — inbox from Connie, 2026-07-24

Connie shared 8 ops-console screens (full-desktop composite + labelled breakdown). Logged here so the PR has a paper trail per [design/README.md](../README.md) rule 3 — the actual PNG exports still need to land in this folder (see "Still needed" below).

## Screens received → docs/04 mapping

| # | Screen (as sent) | docs/04-UI-BRIEF.md section |
|---|---|---|
| 1 | Community Operations Center (overview: safe/medium/high risk counts, live community map, live alerts, quick actions) | §2 map screen + §2 live feed |
| 2 | Live AI Camera — Vision Engine (camera feed, face/vehicle/plate detection results, risk score, actions) | §2 alert card anatomy — this is the detail-on-click view of a detection |
| 3 | Crime Intelligence & Forecasting (peril forecast %, risk forecast chart, top risk areas, incidents by peril) | §2 forecast layer / docs/02 §5 forecasting stack output |
| 4 | Patrol Command Center (optimized routes map, unit roster, route summary, deploy) | §2 routes panel — Koper dwell + coverage/fuel counters |
| 5 | Investigation Workspace (case details, AI findings, evidence timeline, reconstructed route) | §2 entity detail — factor breakdown + trajectory, closest to Sighting Graph F1–F6 |
| 6 | Member App Preview (mobile: home risk score, vehicle, safe route, SOS) | §3 member view |
| 7 | Live Alerts Center (alert list + filters + alert detail panel) | §2 live feed / verify queue — **this is the human-gate screen, docs/04 §4 law 1: Verify must be primary, not Dispatch** |
| 8 | Claims & Analytics Dashboard (claims totals, patrol peril donut, claims over time, top areas/vehicles/perils) | exec view (§1: third priority, can be one tab) — maps to docs/05 claims levers |

## Flagged before merge — not silent per design/README.md rule 3

**Branding says "VUKA by Discovery" on every screen.** Our product is **BEACON** (ADR-0003) — the rename specifically severed the VUKA name so we could align to Discovery's own brand language ("the light that stays on" ties to Discovery's "protect their lives" purpose clause, docs/05 §1b). Reusing VUKA's *design tokens* is correct and expected (docs/04 §5 says to); reusing the VUKA *wordmark/logo* is not — that needs to be BEACON before this ships in the pitch. Swap:
- Sidebar logo/wordmark: "VUKA by Discovery" → "BEACON by Discovery" (or "BEACON — the light that stays on", keep the Discovery lockup if that's the shared-value framing from docs/05 §1)
- No other content changes needed — the screen layouts, IA, and detection/forecast/patrol logic all look right against docs/04.

**Alert-detail panel default action:** screen 7's alert detail shows "View in Investigation" as the only prominent action — worth double-checking it doesn't silently skip the verify step (docs/04 §4 law 1: Verify always primary, never a one-click Dispatch/auto-escalate). Flagging for Connie to confirm intent, not blocking.

## Still needed to close this PR
Per [design/README.md](../README.md) rules 1–2: drop the actual PNG exports in this folder, one per screen, named `2026-07-24_<screen-name>_v1.png` (e.g. `2026-07-24_community-operations-center_v1.png`), plus the Figma share link in the PR description.
