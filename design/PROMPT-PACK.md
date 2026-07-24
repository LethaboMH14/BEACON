# BEACON — Claude Design prompt pack

> Owner: Lethabo. Status: v1.0, 2026-07-25. Use with `design/README.md` (filenames, PR rules) and `docs/04-UI-BRIEF.md` (the four UI laws).
> **How to use:** paste §1 **verbatim at the top of every prompt**, then paste the one screen block from §2 underneath it, then attach your reference images.
> The preamble is what makes twelve separately-generated screens look like one product instead of twelve mockups — do not skip it, do not paraphrase it.

---

## 1. The constant preamble (paste before every screen prompt)

```
You are designing screens for BEACON — a real-time community safety platform built for
Discovery (South African insurer). Tagline: "the light that stays on."

This is a production security-operations product, not a concept piece. It will be judged by
engineers and insurance executives. It must look like software that is already deployed and
being used by a real security company tonight — not like a dribbble shot, and not like a
template. Dense, confident, calm. Real data density over decorative whitespace.

DESIGN LANGUAGE
- Mood: futuristic but restrained. Think Linear, Vercel dashboard, Arc, Stripe Radar,
  Palantir Foundry — precision instruments, not consumer apps. Zero playfulness.
- Depth: soft, layered surfaces. Subtle elevation via low-opacity borders (1px, white at 6-8%
  on dark / black at 6% on light) plus very soft shadows. NO hard drop shadows, NO glassmorphism
  blur soup, NO neon glow except on genuine live/alert states.
- Corners: 12px on cards and panels, 10px on buttons and inputs, 999px on pills and chips.
- Buttons: soft, generously padded, subtle inner highlight on the primary. Primary uses the
  accent gradient. Secondary is a bordered ghost. Destructive/escalation actions are visually
  quieter than the safe action, never louder.
- Motion (describe it, even in a static frame): everything eases, nothing snaps. Live data
  arrives with a gentle slide-and-fade from the top of a list.

COLOUR TOKENS (use these exact values)
Dark chrome (headers, nav, ops shell):
  --bg-900: #0A0F1A     canvas
  --bg-800: #101725     panel
  --bg-700: #182130     raised / hover
  --line-dark: rgba(255,255,255,0.08)
  --text-hi: #F1F5F9    --text-mid: #94A3B8    --text-lo: #64748B
Light content (data panels, member view, exec view):
  --bg-50: #F7F9FC      canvas
  --bg-0:  #FFFFFF      card
  --line-light: rgba(15,23,42,0.08)
  --ink-hi: #0F172A     --ink-mid: #475569     --ink-lo: #94A3B8
Brand:
  --beacon: #F5A623     signal amber — the beacon light. Use SPARINGLY: live indicators,
                        the active nav pill, the primary CTA gradient. It is a signal, not a theme.
  --beacon-grad: linear-gradient(135deg, #F5A623 0%, #F27B21 100%)
  --discovery: #0B5FA5  deep institutional blue — trust, structure, chart primaries
  --discovery-soft: #E8F1F9
Risk ramp (ONLY for risk/severity, never decoration):
  --safe: #10B981   --watch: #F59E0B   --high: #F0653A   --critical: #E11D48
Semantic:
  --live: #22D3EE   pulsing cyan dot for a live stream
  --stale: #6B7280  greyed + always paired with a timestamp

TYPE
- Family: Inter (or system equivalent). Nothing decorative.
- Scale: 11/12 uppercase 0.06em tracking for labels · 13 body · 15 emphasis · 20 panel title ·
  32-44 for the single hero metric on a screen.
- ALL numerals tabular/monospaced-figures so live-updating values do not jitter.
- Sentence case everywhere except the small uppercase labels.

NON-NEGOTIABLE PRODUCT RULES (these are enforced in our code — the design must obey them)
1. "Verify" is ALWAYS the visually primary action. "Dispatch armed response" is ALWAYS
   secondary and behind a confirmation. Never make escalation the easy click.
2. Show exactly ONE confidence number per detection — a single calibrated percentage with a
   bar. Never show raw per-model scores. Always accompany it with 2-5 factor chips explaining
   WHY (e.g. "3rd sighting · 00:14 · near-repeat zone · weapon-candidate").
3. Anything actionable and irreversible has a visible countdown cancel ring (15s).
4. Stale data is greyed and stamped with its age. NEVER blank, never silently fresh-looking.
5. Simulated data carries a small "SIMULATED" corner tag.
6. Copy is legally careful: "weapon-candidate detected", "possible repeat sighting",
   "unusual activity". NEVER "criminal identified", "threat confirmed", "suspect".

OUTPUT
Produce a complete, self-contained, responsive React + TypeScript + Tailwind screen.
Realistic South African placeholder data (Johannesburg suburbs: Soweto, Sandton, Randburg,
Midrand, Roodepoort, Alexandra; SA plate format e.g. "JZ 84 KL GP" — fake plates only).
No lorem ipsum. No stock-photo faces — use neutral silhouettes or blurred placeholders.
```

---

## 2. Screen prompts

Order matters — **build 2.1, 2.3 and 2.7 first**; those three carry the demo. Everything else is upside.

### 2.1 Ops console — Community Operations Centre (the home screen, most demo minutes)

```
SCREEN: Community Operations Centre — the primary ops console home. This is on screen for most
of a 9-minute live demo, so it must read instantly from across a room and still reward a close look.

Dark chrome shell:
- Top bar: BEACON wordmark + "by Discovery" lockup, left. Nav pills centre: Overview · Live Camera ·
  Intelligence · Patrol · Investigations · Claims. Right: demo clock reading 00:14, a live-status
  cluster (green "12 cameras online", amber "2 offline"), operator avatar + name.
- Body is a 3-panel layout, light content panels floating on the dark canvas:

LEFT (dominant, ~55%): live hex map of Johannesburg. H3 hexagons shaded on the risk ramp,
semi-transparent over a dark basemap. Camera pins (green live / grey offline / amber pre-armed).
A floating layer-toggle card top-left: Past claims · Forecast (next 24h) · Patrol routes · Cameras.
A horizontal 00h-23h time scrubber pinned along the bottom of the map with the handle at 00:14 and
a small histogram of claim density behind the track — the midnight spike must be visible in the track itself.

RIGHT TOP (~45% x 60%): "Live feed" — a streaming vertical list of sighting and alert cards, newest
at top. Each card: small dark clip thumbnail with a detection box drawn on it, entity label
("Vehicle · JZ 84 KL GP"), the ONE calibrated confidence as a percentage plus a thin bar, 3-4 factor
chips, relative timestamp, and a compact action row [Verify] [Dismiss]. The top card is mid-escalation:
it has a countdown cancel ring and a soft amber edge glow.

RIGHT BOTTOM (~45% x 40%): three stat tiles in a row — "Active alerts 3", "Candidates awaiting
verification 7", "Units deployed 4/6" — each with a 24h sparkline. Below them, a compact
"Tonight's forecast" strip: top 3 risk hexes as named suburbs with a risk percentage and trend arrow.

Show one card in the feed carrying a "SIMULATED" corner tag so the labelling convention is visible.
```

### 2.2 Ops console — Live AI Camera / Vision Engine

```
SCREEN: Live AI Camera — the vision engine detail view. This is the screen that proves the computer
vision is real, so the feed must dominate and the machine's reasoning must be legible beside it.

- Left ~65%: the live camera frame, large, dark, with real-looking detection overlays — thin 2px
  boxes in the risk-ramp colours, each with a small label tag above it ("person 0.91",
  "vehicle 0.88", "plate JZ 84 KL GP", "weapon-candidate 0.62"). A subtle scanline/corner-bracket
  treatment on the frame edges reads as "machine vision" without being cheesy. Bottom-left of the
  frame: camera id, suburb, resolution, live cyan pulse dot + "LIVE".
- Right ~35%, a stacked column of analysis cards:
  1. "Plate recognition" — the OCR'd plate rendered large in a plate-styled chip, a confidence
     percentage, and a WATCHLIST MATCH banner in critical red with the reason ("flagged 2026-07-19,
     Randburg — 3 prior sightings").
  2. "Detections this frame" — a compact table: class, confidence, first-seen.
  3. "Audio" — a small live waveform with classified events listed beneath it ("glass break 0.71",
     "raised voices 0.44") — this is the multi-modal proof, make it feel co-equal to the video.
  4. "Fused assessment" — the single calibrated number, big, with the factor chips beneath and the
     current state as a pill: SAFE / WATCH CANDIDATE / FLAGGED. Directly beneath it, in plain text:
     "Machine ceiling reached — human verification required to escalate." Then [Open verify queue]
     as the primary action.
- Below the frame: a horizontal filmstrip of the last 6 detection thumbnails, scrubbable.
```

### 2.3 Ops console — Verify queue / human gate (**the ethics screen — make it the most beautiful one**)

```
SCREEN: Verify queue — where a human operator decides. Our entire ethics story lives here, and a
judge will be invited to make the call on this screen personally. It should feel like a considered
instrument, not an alarm: calm, evidential, unhurried. Resist red. This is a screen for thinking.

- Left rail ~22%: the queue — candidates awaiting verification, each a compact row with thumbnail,
  entity label, confidence, and time waiting. One row is selected with an amber left border.
- Centre ~50%: the evidence panel for the selected candidate, laid out as a case, not a feed:
  · Header: entity label, current state pill "WATCH CANDIDATE", the one calibrated confidence.
  · A horizontal sighting timeline — 3 nodes on a rail (Camera 04 · 23:41, Camera 07 · 00:02,
    Camera 04 · 00:14) with a thumbnail at each node and a mini-map beside it showing the three
    points and the path between them.
  · "Why this was raised": the factor chips expanded into full labelled rows — factor name, its
    contribution to the score as a small bar, and a plain-English sentence for each
    (F1 recurrence, F2 timing, F3 near-repeat zone, F6 audio corroboration).
  · "Checks run": whitelist check result, embedding match strength with its threshold shown,
    plate-match confidence. Each with a clear pass/fail/inconclusive state.
- Right ~28%: the decision column.
  · Primary, large, full-width: [Flag for response] — but styled as a considered commitment
    (solid, confident, NOT alarming red; use the accent gradient).
  · Equal-weight secondary: [Dismiss — no action] and [Add to whitelist].
  · A required note field: "Reason for decision (recorded to the evidence chain)".
  · Beneath: "Signed as: Op. N. Dlamini · 00:14:22 · this decision is permanently recorded" with a
    small chain-link icon.
  · At the very bottom, quiet and small: "Dispatch armed response" as a text link, requiring
    confirmation — visually the least prominent thing on the screen.
```

### 2.4 Ops console — Crime Intelligence & Forecasting

```
SCREEN: Crime Intelligence — the forecasting view. Analytical, chart-dense, executive-legible.

- Hero row: four metric tiles — "Forecast risk, next 24h" as a large percentage with a confidence
  interval band, "Top peril: vehicle theft 61%", "Hexes above threshold: 14", "Model: v0.4 ·
  calibrated" with a small "how this is calculated" info affordance.
- Main chart, wide: predicted risk over the next 24 hours as a smooth area chart with a shaded
  uncertainty band, the midnight peak clearly the tallest point, plus a faint dotted line showing
  the naive historical baseline behind it so the uplift is visually obvious.
- Left of it: "Top risk areas" — a ranked list of suburbs, each with a risk score, a trend arrow,
  and a horizontal micro-bar.
- Below: two charts side by side — incidents by peril (horizontal bars, not a pie) and claims over
  time (12-month line with a seasonal shade).
- Right rail: "Contributing factors" — a stack of weighted rows (near-repeat contagion, hour of day,
  payday proximity, load-reduction stage, weather, historical density) each with a contribution bar.
  Below it a small honest caption: "Contributions are model attributions, not causes."
Every number on this screen must look like it came from a query — no invented precision, no
suspiciously round figures.
```

### 2.5 Ops console — Patrol Command Centre

```
SCREEN: Patrol Command — route optimisation and unit dispatch.

- Left ~60%: map with optimised patrol routes drawn as smooth coloured polylines, numbered stop
  markers along each, and the risk hexes faintly visible underneath so the route visibly targets
  the hot cells. A small legend maps route colour to team.
- Right ~40%:
  · "Tonight's plan" summary card with animated counters: "Fuel −34%", "Coverage 82% of top-risk
    hex-hours", "6 units · 23 stops". Each counter has a small caption naming its source
    ("vs. fixed-route baseline").
  · Unit roster: rows with team name, status pill (En route / At stop / Idle), current assignment,
    and a dwell countdown ("8:12 remaining of 12:00") as a thin ring.
  · Stop list for the selected team: sequence, suburb, arrival window, dwell duration, risk score.
  · Primary action [Plan routes] and secondary [Dispatch all] — dispatch behind confirmation.
- A quiet caption under the counters: "Dose length 11-15 min per Koper's patrol-decay curve."
```

### 2.6 Ops console — Investigation Workspace

```
SCREEN: Investigation Workspace — the case file after an incident, and the screen we close the demo on.

- Left rail: case list, one selected.
- Centre: the case. Header with case id, status, severity, linked entity. Then a vertical evidence
  timeline — each entry a row with an icon, timestamp, actor ("System" vs. a named operator), the
  action, and a truncated SHA hash chip on the right. Consecutive entries are visually linked by a
  chain line down the left gutter, and a header banner states "Evidence chain intact — 9 records
  verified" with a small verified icon.
- Right rail: "AI findings" — the reconstructed entity route on a mini-map with a trajectory cone,
  the factor breakdown, and linked sightings as thumbnails.
- Top-right action: [Export report] as the primary — and design the exported report preview too:
  a clean, printable, document-styled panel with the hash chain rendered as a verifiable list.
  Caption honestly: "Structured to support an investigation. Tamper-evident." Never "court-admissible".
```

### 2.7 Member app — Home (mobile, in a phone frame)

```
SCREEN: BEACON member app home, mobile 390x844, presented inside a soft realistic phone frame on a
neutral backdrop. Light theme, calm, reassuring — this is a consumer product for someone who is
occasionally frightened. Warm not clinical, but never cute.

- Header: greeting, suburb, a small live cyan dot with "Home protected".
- Hero: tonight's street safety score as a large number inside a soft circular gauge on the risk
  ramp, with one plain sentence beneath: "Slightly elevated for your area tonight — vehicle theft
  risk peaks around midnight."
- Below: a horizontal row of soft tiles — My cameras (2 live) · Safe route · My guardians (3) ·
  Privacy centre. Each with an outline icon and a status line.
- An "Active alert" card if present: thumbnail, "Unusual activity at your driveway", the one
  confidence number in soft language, timestamp, and two actions: [I'm fine] primary and
  [Alert my guardian] secondary.
- Vitality Protect strip: points earned this month, premium-discount line, subtle Discovery-blue.
- Bottom nav: Home · Cameras · Routes · Alerts · Profile.
- A large SOS control that is unmistakable but not screaming — a soft-edged circular button, held
  rather than tapped, with a "hold 3s" affordance.
```

### 2.8 Member app — Alert detail

```
SCREEN: Member alert detail, mobile 390x844 in a phone frame. This is the emotional beat of the
demo — an alert has just landed. Soft, clear, and it must not induce panic.

- Top: the clip thumbnail (or looping video placeholder) with the detection box drawn softly, and a
  "SIMULATED" tag if applicable.
- Headline in plain human language: "Unusual activity at your driveway" — never a threat assertion.
- The single confidence rendered as plain language plus the number: "High confidence (87%)" with a
  soft bar, then the factor chips in consumer wording: "Seen 3 times · Late night · Unfamiliar vehicle".
- A prominent countdown cancel ring: "Alerting your guardian in 12s" with [I'm fine — cancel] as the
  visually dominant action.
- Then, in descending prominence: [Alert my guardian] · [Call armed response]. Armed response is the
  quietest and requires a confirm step.
- Bottom: a "What happens next" expandable — plain-language, three steps.
- A small privacy line: "This clip is stored encrypted and only you and your guardians can open it."
```

### 2.9 Member app — Live camera + 2.10 Safe route

```
SCREEN A: Member live camera, mobile. Live feed at top with soft detection overlays, camera selector
chips beneath, a detection card ("Vehicle detected · 2 min ago") with confidence and factor chips,
and actions [Save clip] [Share with guardian] [Report]. An arm/disarm toggle with an explicit state
label. Privacy caption: "Faces are matched as encrypted signatures, not stored photos."

SCREEN B: Safe route, mobile. Map with two or three route options drawn, each as a selectable card
below showing duration, a safety score, and what makes it safer ("passes 4 monitored cameras ·
2 patrol units active"). Risk hexes faintly overlaid. Primary [Start route]. During-route state:
a slim top bar with next turn plus a live safety indicator.
```

### 2.11 Patrol officer (mobile, on-shift)

```
SCREEN: Patrol officer on-shift view, mobile, DARK theme (this is used at night in a vehicle —
high contrast, large touch targets, glanceable).

- Top: shift status, team name, time on shift.
- Hero card: "Next stop" — suburb, ETA, distance, risk score, and the dwell timer as a large ring
  ("Dwell 12:00").
- If assigned: an "Active incident" card in the risk ramp with the incident summary, confidence,
  and [Navigate] + [Arrived at scene] as large primary buttons.
- Route progress: a vertical stop list with completed stops checked, the current one highlighted,
  upcoming ones dimmed.
- Bottom: a large [Report from scene] button and an emergency backup control.
```

### 2.12 Discovery exec view — Claims & portfolio analytics

```
SCREEN: Executive analytics — light theme, boardroom-legible, Discovery blue as the chart primary.
This is the money screen; it should look like something an exec would screenshot into a board pack.

- Hero metrics row: total claims value, claims count, average claim, "projected claims avoided"
  (clearly labelled as a projection with its assumption stated inline, not hidden).
- Main: claims over time, 12-month line, with a clearly annotated marker where BEACON coverage
  began and a shaded projected divergence after it — the divergence must be visually labelled
  "projected" and styled differently (dashed) from actual.
- Supporting: peril split (horizontal bars: vehicle-related 93.6%, other 6.1%), top 10 suburbs by
  claims value, claims by hour with the midnight spike, network growth (cameras + members over time).
- Right rail: "Shared value loop" — a compact diagram of the Vitality Protect flywheel
  (member protects → fewer claims → lower premium → more members).
- Footer caption, small: "All figures derived from 15,712 claims records. Projections labelled as
  such and traceable to their query."
```

---

## 3. Where output lands (the handoff convention)

```
design/
├── PROMPT-PACK.md              ← this file
├── ops-console/                ← PNG exports, YYYY-MM-DD_screen-name_v1.png
├── member-view/
├── patrol/
├── exec-view/
└── exports/                    ← raw, UNMODIFIED Claude Design code exports, one folder per screen
                                   (kept so we can always diff our edits against the original)

dashboard/                      ← the real React app (Vite + React + TS + Tailwind)
├── src/
│   ├── screens/                ← ported screens live here
│   ├── components/             ← anything used by 2+ screens gets extracted to here
│   ├── theme/tokens.ts         ← the §1 tokens, as the single source of truth
│   └── api/                    ← WS + REST clients against the real server
```

**Rules:**
1. Every screen lands as **both** a PNG in the view folder **and** its raw code export in `design/exports/`. The PNG is the record if the code needs rework; the code is the head start.
2. Raw exports are never edited in place — port into `dashboard/src/screens/`, then edit there.
3. `theme/tokens.ts` wins over anything hardcoded in a generated screen. First job when porting a screen is replacing its literal hex values with token references — this is what stops twelve screens drifting apart.
4. Everything goes in via PR per `design/README.md`, and the PR names which docs/04 screen it implements and flags any deviation from the four UI laws.

## 4. What to send back for the fastest turnaround

When you have output from Claude Design, send me: the screenshot, plus which screen block from §2 it
came from, plus anything you want changed. Prompt-refinement notes go under §5 below so the pack
improves as we go rather than the same fix being re-typed every round.

## 5. Prompt refinements (append as we learn)

_(empty — add dated notes here as screens come back and prompts get tuned)_
