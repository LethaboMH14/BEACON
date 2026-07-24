# Member-view mockups — inbox from Connie, 2026-07-24

Second mockup set: 5 phone screens, correctly branded **BEACON — "the light that stays on"** (no VUKA-branding issue this time). Logged here per [design/README.md](../README.md) rule 3; PNG exports still need to land in this folder.

## Screens received → docs/04 mapping

| # | Screen | docs/04-UI-BRIEF.md section | Notes |
|---|---|---|---|
| 1 | Home Dashboard (safety score, active alert, camera/route/guardian tiles, SOS) | §3 member view | Matches brief closely |
| 2 | Live Camera (driveway feed, vehicle detection card, clip/evidence/share actions) | §3 member view — camera detail | Detection card mirrors ops-console screen 2's anatomy (good consistency) |
| 3 | Alert Details ("I'm Safe" / "Call Guardian" / "Call Security") | §3 member view — alert detail | See flag below |
| 4 | Safe Route (map, route options, patrol/camera overlay) | §3 member view — safe route | Matches brief |
| 5 | **Patrol Officer** (on-duty command: next stop, current incident, route progress, arrived-at-scene) | **not in original docs/04 scope** | New role — see below |

## New role surfaced: Patrol Officer view

docs/04 §1 scoped three dashboards (ops console primary, member/guardian second, exec third). Connie's screen 5 is a fourth: a **patrol officer's on-shift mobile view** — next stop, live incident assignment, route progress, arrive-at-scene confirm. This is a genuinely good addition: it closes the loop between the ops console's route-dispatch (docs/01 §2.5 routes panel) and an actual human doing the patrol, which nothing else in the doc pack currently covers.

**Not blocking, but needs a decision before it's built out:** is this in scope for the pitch (P0/P1) or a roadmap slide? Recommend folding it into docs/04 as a fourth view — flagging for Connie/team to confirm scope, not deciding unilaterally here.

## Flagged — not silent per design/README.md rule 3

**Screen 3 "Call Security: Armed response" button.** Worth confirming this is real (dispatches to an actual private-security integration) vs. aspirational copy for the pitch — docs/06 §6 honesty ledger requires anything we say out loud in the demo to be labelled `sim_` if it's not real. If this button is demo-real, fine as-is; if it's a mocked action for now, the pitch narration needs to say so explicitly when this screen is shown.

**Branding: correct.** BEACON wordmark + tagline used consistently — no fix needed here (contrast with the ops-console set, which still needs the VUKA→BEACON swap).

## Still needed to close this PR
Per [design/README.md](../README.md) rules 1–2: PNG exports named `2026-07-24_<screen-name>_v1.png` in this folder, plus the Figma link in the PR description.
