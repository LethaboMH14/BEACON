# Handoff: BEACON — Community Safety Platform (Discovery)

## Overview
BEACON is a real-time community safety platform for Discovery (South African insurer). Tagline: "the light that stays on." This bundle covers 11 screens spanning the security-operations console (ops centre, verify queue, live AI camera, crime intelligence, patrol command, investigation workspace, executive analytics) and the consumer mobile app (member home, alert detail, live camera, safe route, patrol officer shift).

## About the Design Files
The files in `screens/` are **design references built in HTML** (React-like component runtime, inline styles, static/mock data) — they show intended look, layout, copy and interaction, not production code to copy directly. The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, native, etc.) using its established patterns, state management, real APIs and libraries — or, if no environment exists yet, choose the most appropriate stack (React + TypeScript + Tailwind is a good fit given the original design brief) and implement there.

Each `.dc.html` file is self-contained and can be opened directly in a browser to inspect the rendered design. `ios-frame.jsx` is a reusable iOS device-bezel component used to preview the mobile screens; `support.js` is internal runtime plumbing for the design tool and is **not** meant to ship — ignore it when recreating in your codebase.

## Fidelity
**High-fidelity.** All colors, type sizes, spacing, corner radii, and copy are final per the design system below. Recreate pixel-perfectly using your codebase's component library, substituting mock data for real API calls.

## Design system

### Colour tokens (exact values)
Dark chrome (headers, nav, ops shell):
- `--bg-900: #0A0F1A` canvas
- `--bg-800: #101725` panel
- `--bg-700: #182130` raised / hover
- `--line-dark: rgba(255,255,255,0.08)`
- `--text-hi: #F1F5F9` `--text-mid: #94A3B8` `--text-lo: #64748B`

Light content (data panels, member view, exec view):
- `--bg-50: #F7F9FC` canvas
- `--bg-0: #FFFFFF` card
- `--line-light: rgba(15,23,42,0.08)`
- `--ink-hi: #0F172A` `--ink-mid: #475569` `--ink-lo: #94A3B8`

Brand:
- `--beacon: #F5A623` signal amber — use sparingly: live indicators, active nav pill, primary CTA gradient
- `--beacon-grad: linear-gradient(135deg, #F5A623 0%, #F27B21 100%)`
- `--discovery: #0B5FA5` deep institutional blue — trust, structure, chart primaries
- `--discovery-soft: #E8F1F9`

Risk ramp (ONLY for risk/severity, never decoration):
- `--safe: #10B981` `--watch: #F59E0B` `--high: #F0653A` `--critical: #E11D48`

Semantic:
- `--live: #22D3EE` pulsing cyan dot for a live stream
- `--stale: #6B7280` greyed, always paired with a timestamp

### Typography
- Family: Inter (loaded via Google Fonts in each file), system-ui fallback.
- Scale: 11/12px uppercase, 0.06em tracking for labels · 13px body · 15px emphasis · 20px panel title · 32–44px for a screen's single hero metric.
- All numerals use `font-variant-numeric: tabular-nums` so live-updating values don't jitter.
- Sentence case everywhere except small uppercase labels.

### Shape & elevation
- Corners: 12px cards/panels, 10px buttons/inputs, 999px pills/chips.
- Elevation: 1px low-opacity borders (white 6–8% on dark, black 6–8% on light) + very soft shadows only. No hard drop shadows, no glassmorphism blur, no neon glow except genuine live/alert states (the cyan live dot, amber escalation glow).
- Buttons: generously padded, soft corners. Primary = accent gradient with a subtle inset top highlight. Secondary = bordered ghost. Destructive/escalation actions are always visually quieter than the safe action — never louder, never the easy click.
- Motion (to implement with real transitions): everything eases (ease-in-out, ~200–300ms), nothing snaps. New live-feed items should slide-and-fade in from the top of the list.

## Non-negotiable product rules (encoded in the reference designs — must be preserved in implementation)
1. **"Verify" is always the visually primary action.** "Dispatch armed response" is always secondary and sits behind a confirmation step. Never make escalation the easy click.
2. **Exactly one confidence number per detection** — a single calibrated percentage with a bar. Never show raw per-model scores. Always pair it with 2–5 factor chips explaining why (e.g. "3rd sighting · 00:14 · near-repeat zone · weapon-candidate").
3. **Anything actionable and irreversible has a visible 15s countdown cancel ring** before it executes (see the escalating live-feed card, the member alert detail screen, the dispatch-confirm rows).
4. **Stale data is greyed and stamped with its age** — never blank, never silently fresh-looking.
5. **Simulated/demo data carries a small "SIMULATED" corner tag** (see one live-feed card and the member alert clip thumbnail).
6. **Copy is legally careful**: "weapon-candidate detected", "possible repeat sighting", "unusual activity". Never "criminal identified", "threat confirmed", "suspect", or "court-admissible" (the investigation report caption says "tamper-evident," not "court-admissible").

## Screens

### 1. Community Operations Centre (`Community Operations Centre.dc.html`) — desktop, 1920×1080 target, dark shell
Primary ops console home, on screen for most of a live demo.
- **Top bar** (60px, dark `#0A0F1A`, border-bottom `--line-dark`): BEACON wordmark + "by Discovery" lockup (left) · nav pill cluster centered (Overview · Live Camera · Intelligence · Patrol · Investigations · Claims — active pill uses the beacon gradient, others `#94A3B8` text on transparent) · right cluster: demo clock (00:14, tabular nums), online/offline camera counts, operator avatar + name.
- **Body**: 3-panel flex row, 14px gap/padding.
  - **Left (flex 55%)**: dark map panel with a generated H3-style hex grid (pointy-hex `clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)`), risk-ramp colored by proximity to hotspot coordinates, camera pins (green=online, grey=offline, amber=pre-armed). Floating top-left "Map layers" card (Past claims, Forecast, Patrol routes, Cameras — checkbox rows). Top-right risk legend. Bottom-pinned time scrubber card: 24-bar histogram of claim density (midnight bar highlighted red, current position amber) with a vertical amber handle at the current hour.
  - **Right top (~60% of right column)**: "Live feed" — light card, scrollable list of sighting/alert cards (thumbnail w/ detection box, entity label, confidence % + bar, factor chips, relative timestamp, Verify/Dismiss). Top card shows an active escalation state instead of actions: a 15s SVG countdown ring, "Dispatching armed response," and a Cancel button, with a soft amber border glow (`animation: escalGlow`). One card carries the SIMULATED corner tag.
  - **Right bottom (~40%)**: 3 stat tiles in a grid (Active alerts, Awaiting verification, Units deployed) each with a mini SVG sparkline, then a "Tonight's forecast" list of 3 named suburbs with risk % and trend arrow.
- Shell min-width 1360px with horizontal scroll below that (rather than letting the nav clip/overlap).

### 2. Verify Queue (`Verify Queue.dc.html`) — desktop, dark shell + light panels
The human-verification screen — calm, evidential, not alarm-toned. Resists red.
- **Left rail (22%)**: scrollable queue list, rows with thumbnail/entity/confidence/waiting time; selected row gets a white background + amber left border.
- **Centre (50%)**: header (entity label, amber "Watch candidate" state pill, big calibrated confidence % + bar) · sighting timeline (3 nodes on a rail with thumbnails + camera/timestamp, plus a small SVG mini-map showing the path between sighting points) · "Why this was raised" factor rows (name, contribution % bar in Discovery blue, plain-English sentence) · "Checks run" (whitelist / embedding-match / plate-match, each a pass/fail/inconclusive badge).
- **Right (28%)**: decision column — large full-width "Flag for response" primary button (beacon gradient), equal-weight "Dismiss — no action" / "Add to whitelist" secondary buttons, a required "Reason for decision" textarea, a signed-and-recorded caption with a chain-link icon, and at the very bottom a small underlined text link "Dispatch armed response" that expands an inline Confirm/Cancel row — the least visually prominent control on the screen.

### 3. Live AI Camera (`Live AI Camera.dc.html`) — desktop, dark shell
Vision-engine detail view proving the CV pipeline.
- **Left (65%)**: large dark camera frame with a subtle scanline pass, 4 corner brackets (machine-vision framing), and absolutely-positioned detection boxes (risk-ramp colored 2px borders with a label tag above each: "person 0.91", "vehicle 0.88", "plate JZ 84 KL GP", "weapon-candidate 0.62" in critical red). Bottom-left overlay: live cyan pulse + "LIVE", camera id/suburb, resolution. Below the frame: a horizontal scrubbable filmstrip of 6 thumbnails, the current one amber-bordered.
- **Right (35%)**, stacked light cards: **Plate recognition** (monospace plate chip, OCR confidence, critical-red "Watchlist match" banner with reason) · **Detections this frame** (class/confidence/first-seen table) · **Audio** (mini waveform bars + classified events with confidence, positioned as co-equal proof to video) · **Fused assessment** (big single confidence %, state pill, factor chips, "Machine ceiling reached — human verification required to escalate," and a primary "Open verify queue" button that links to the Verify Queue screen).

### 4. Crime Intelligence (`Crime Intelligence.dc.html`) — desktop, dark shell
Forecasting/analytics view.
- **Hero row**: 4 tiles — forecast risk next 24h (with ± confidence interval), top peril, hexes above threshold, model version with a hover "i" info affordance.
- **Main chart row**: left "Top risk areas" ranked list (suburb, score, trend arrow, micro-bar; suburb names truncate with ellipsis rather than wrap) beside a wide smooth area chart (forecast line, shaded uncertainty band, dotted historical-baseline line behind it, midnight peak marked with a dot).
- **Two charts below**: incidents-by-peril horizontal bars, and a 12-month claims line chart with a shaded seasonal band.
- **Right rail**: "Contributing factors" weighted bars (near-repeat contagion, hour of day, payday proximity, load-reduction stage, weather, historical density) with the honest caption "Contributions are model attributions, not causes."

### 5. Patrol Command (`Patrol Command.dc.html`) — desktop, dark shell
Route optimisation and dispatch.
- **Left (60%)**: hex-map background (same generator as Ops Centre) with 4 team routes drawn as colored SVG polylines, numbered stop markers, and a top-left legend mapping route color → team name (fixed min-width, nowrap labels so long team names never wrap/overlap).
- **Right (40%)**: "Tonight's plan" summary (Fuel −34%, Coverage 82%, 6 units·23 stops — each captioned with its baseline source) plus the Koper's patrol-decay caption · unit roster (status pill En route/At stop/Idle, dwell countdown as a thin SVG ring for at-stop units, click to select) · stop list for the selected unit (sequence, suburb, arrival window, dwell, risk score) · primary "Plan routes" + secondary "Dispatch all" (behind an inline confirm).

### 6. Investigation Workspace (`Investigation Workspace.dc.html`) — desktop, dark shell + light panels
Post-incident case file; the demo's closing screen.
- **Left rail**: case list (id, entity, severity pill, status), one selected.
- **Centre**: case header (id, severity, entity, status) + "Export report" primary button · green "Evidence chain intact — N records verified" banner · vertical evidence timeline (each row: time, actor [System vs named operator, nowrap], action text, truncated monospace SHA hash chip [nowrap], connected by a left-gutter chain line).
- **Right rail**: "AI findings" — reconstructed route mini-map with a trajectory cone at the last point, factor breakdown bars, linked-sighting thumbnails grid.
- **Export report** opens a fixed-position modal styled as a printable document: report title/generated-by line, a 2×2 summary grid, the same evidence chain rendered as a plain verifiable list, and the caption "Structured to support an investigation. Tamper-evident." (never "court-admissible").

### 7. Executive Analytics (`Executive Analytics.dc.html`) — desktop, dark shell + light panels
Board-pack-legible exec view, Discovery blue as chart primary.
- **Hero row**: total claims value, claims count, average claim, and "Projected claims avoided" — explicitly labelled as a projection with its assumption stated inline (never hidden).
- **Main chart**: 12-month claims value line — solid actual, dashed projected continuation, dotted "without BEACON (modelled)" baseline, shaded divergence between them, and a vertical amber dashed marker labelled "BEACON coverage began."
- **2×2 supporting grid**: peril split horizontal bars (vehicle-related 93.6% / other 6.1%) · claims-by-hour 24-bar histogram (midnight spike) · top-10-suburbs ranked bars (names truncate, don't wrap) · network growth dual-line chart (cameras + members over 12 months).
- **Right rail**: "Shared value loop" — 4 stacked cards (Member protects → Fewer claims → Lower premium → More members) connected by down-arrows plus a "loops back" caption.
- **Footer caption**: "All figures derived from 15,712 claims records. Projections labelled as such and traceable to their query."

### 8. Member App Home (`Member App Home.dc.html`) — mobile 390×874, iOS frame, light theme
Consumer home screen, warm/reassuring, never cute.
- Greeting + suburb (left), live cyan "Home protected" pill (right).
- Hero: circular gauge (score 62/100, watch-amber arc) with a plain-language risk sentence beneath.
- 2×2 tile grid: My cameras (2 live) · Safe route (active tonight) · My guardians (3 linked) · Privacy centre — each a simple line-stroke icon + status line.
- Active alert card (amber-bordered): thumbnail, headline, one confidence % + bar + soft caption, "I'm fine" (Discovery-blue primary) / "Alert my guardian" (ghost secondary).
- Vitality Protect strip (Discovery-soft background): points this month + premium-discount line.
- Bottom nav (Home active in amber, Cameras/Routes/Alerts/Profile).
- Floating hold-to-activate SOS button (bottom-right): 3-second hold fills an SVG progress ring in critical red before "sending."

### 9. Member Alert Detail (`Member Alert Detail.dc.html`) — mobile, iOS frame, light theme
The emotional core screen — an alert has just landed; must not induce panic.
- Clip thumbnail with a soft amber detection box + SIMULATED tag.
- Plain-language headline ("Unusual activity at your driveway" — never a threat assertion).
- Confidence in plain language + number ("High confidence (87%)") with a soft bar, then factor chips in consumer wording ("Seen 3 times · Late night · Unfamiliar vehicle").
- Prominent 12s countdown cancel ring: "Alerting your guardian in Ns" with "I'm fine — cancel" as the dominant Discovery-blue action.
- Descending-prominence secondary actions: "Alert my guardian" (bordered), "Call armed response" (quietest, muted text-style button, behind an inline confirm).
- Expandable "What happens next" — 3 numbered plain-language steps.
- Small privacy caption: "This clip is stored encrypted and only you and your guardians can open it."

### 10. Member Live Camera (`Member Live Camera.dc.html`) — mobile, iOS frame, light theme
- Live feed frame (soft green detection box, LIVE pill, camera name overlay).
- Horizontal camera-selector chips (Front gate / Driveway / Back yard / Side gate).
- Detection card: headline, relative time, confidence % + bar, factor chips, 3 equal-weight actions (Save clip / Share with guardian / Report).
- Arm/disarm row: tappable toggle switch with an explicit state label ("Armed · monitoring active" in safe-green, or "Disarmed" in muted grey).
- Privacy caption: "Faces are matched as encrypted signatures, not stored photos."

### 11. Safe Route (`Safe Route.dc.html`) — mobile, iOS frame, light theme
- Map area: same hex-risk overlay treatment (faint) + 2–3 selectable route polylines.
- Route option cards below the map (duration, safety score, "what makes it safer" description); selecting one highlights its card border and thickens its map line.
- Primary "Start route" button; once started it flips to a disabled "Route in progress" state and the map header gains a slim overlay bar: next-turn instruction + a live cyan safety-score indicator.

### 12. Patrol Officer Shift (`Patrol Officer Shift.dc.html`) — mobile, iOS frame, **dark theme** (used at night, in-vehicle — high contrast, large touch targets)
- Top: live-status dot, "On shift · Team [name]", time on shift.
- "Next stop" hero card: suburb, ETA, distance, risk score, and a large dwell-timer SVG ring ("12:00").
- Conditional "Active incident" card (risk-ramp tinted background/border): incident summary, confidence %, large "Navigate" (Discovery-blue primary) + "Arrived at scene" (bordered ghost) buttons.
- Route progress: vertical stop list — completed stops checked (green, ✓), current stop highlighted (amber ring + bold text), upcoming stops dimmed grey.
- Bottom: large "Report from scene" primary (beacon gradient) + "Request emergency backup" (quieter, critical-red outline/text — visually restrained per the escalation rule even though it's an officer-safety action).

## Interactions & behavior implemented in the reference (recreate with real state/data)
- Countdown/cancel rings: 15s (ops desktop escalation, verify queue dispatch link) or 12s/3s hold (member alert, member SOS) — implemented via `setInterval` decrementing state and an SVG `stroke-dashoffset` tied to elapsed/total. Cancelling stops the interval and swaps to a resolved-state message.
- Nav pill / unit / case / route selection: simple click-to-select state, highlighted via background + border, no page reload.
- Report/Export modal (Investigation Workspace): fixed-position overlay toggled by boolean state, closes on a "Close" click or (recommend adding) an Escape key / backdrop click in the real implementation.
- Arm/disarm and hold-to-activate SOS: toggle and press-and-hold timers respectively — recreate hold behavior with `pointerdown`/`pointerup`/`pointerleave` (the reference uses mouse+touch handlers).
- "What happens next" accordion: boolean toggle, chevron rotates 180° on open.

## State management
Each screen currently holds only local/component state (selected item, toggle flags, countdown timers) with hardcoded mock data arrays defined in the component. For production:
- Replace mock arrays (queue candidates, live-feed cards, cases, routes, units, chart series) with real API/query results.
- Countdown/escalation timers should be driven by server-authoritative expiry timestamps, not client-only intervals, so a page refresh doesn't reset an in-flight escalation.
- Selected-item state (queue candidate, case, unit, route) is fine as local UI state / URL param.

## Design tokens
See "Colour tokens," "Typography," and "Shape & elevation" above — treat those as the canonical token list (convert to your platform's theme format: CSS variables, Tailwind config, or a native design-token file).

## Assets
No external image assets — all thumbnails/clips are CSS `repeating-linear-gradient` placeholders (dark diagonal stripes) standing in for real camera stills/video frames; replace with real media. Icons are hand-drawn inline SVGs (simple stroke shapes) — swap for your icon system if you have one. Fonts: Inter, loaded from Google Fonts in each file's `<head>`.

## Files
All screens are in `screens/`:
- `Community Operations Centre.dc.html`
- `Verify Queue.dc.html`
- `Live AI Camera.dc.html`
- `Crime Intelligence.dc.html`
- `Patrol Command.dc.html`
- `Investigation Workspace.dc.html`
- `Executive Analytics.dc.html`
- `Member App Home.dc.html`
- `Member Alert Detail.dc.html`
- `Member Live Camera.dc.html`
- `Safe Route.dc.html`
- `Patrol Officer Shift.dc.html`
- `ios-frame.jsx` — shared iOS device-bezel component used by the 5 mobile screens (reference only; not for production use)
- `support.js` — internal design-tool runtime; ignore when recreating in your codebase
