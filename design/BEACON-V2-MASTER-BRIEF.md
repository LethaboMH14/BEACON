# BEACON v2 — Master Brief

**Status:** Draft for build · **Date:** 2026-07-25 · **Owner:** Lethabo
**Purpose:** one document that answers everything the judges will ask, and hands a
buildable spec to Claude Design → Claude Code.

This brief covers, in order:

0. What already exists (so we build on it, not next to it)
1. The two surfaces and the routing model
2. The hotspot map — method preserved, made live
3. Cloud + live database (the direct judge question)
4. Proactive notifications
5. LLM orchestration + where a real agent belongs
6. The news/weather scraper
7. **The UI design prompt** (copy-paste handoff)
8. Demo run-of-show, mapped to the five scenes
9. "How did you do that" — the answers, and the claims we refuse to make

---

## 0. What already exists

I read the repo before writing this. Answering your direct question — *"i dont
know if you are using the whole folder and data"*:

**Yes, the hotspot pipeline is already wired into the running system, and its
method is untouched.** Specifically:

| Artifact | Status |
|---|---|
| `hotspot_pipeline/clean_claims_data.py` | Real, unchanged. 15,712 raw claims → cleaned + 3 audit flags |
| `hotspot_pipeline/build_hotspots.py` | Real, unchanged. Aggregation, severity score, Nominatim geocoding, Leaflet map |
| `hotspots.csv` | 764 hot-spot suburbs (≥5 incidents each) |
| `hotspots_geocoded.csv` | **709 geocoded suburbs** — this is the file the server consumes |
| `hotspot_map.html` | 263 KB self-contained Leaflet map, coordinates baked in |
| `server/scripts/load_hotspots.py` | **Already loads all 709 rows into the DB.** Backfills `hex_id`/`lat`/`lng` onto claim rows and writes one `RiskCell` per suburb at its own real `peak_hour`, `risk_score = severity_score`, `model_version="ndu-hotspot-v1"` |
| `server/src/risk/forecast.py` | 3-tier risk: real `RiskCell` row → honest claims fallback → `no_data`. Ndu's rows win tier 1 |
| `server/src/routing/planner.py` | OR-Tools team-orienteering **patrol** route planner (operator-facing), haversine distances |
| `server/src/api/risk.py` | `GET /v1/risk`, `GET /v1/hotspots`, `POST /v1/risk-cells` |

So the severity score, the 5-incident threshold, the 50/50 frequency-vs-cost
weighting, the per-suburb peak hour/day — all of it is already the live scoring
input. **Nothing in this brief changes that method.** Everything below is
additive.

Two things that already exist but are *not* what you asked for, and must not be
confused with it:

- `planner.py` solves **patrol coverage for security teams** (visit the most risk
  under a fuel budget). That is not "get me home safely." The member-facing
  safest-route feature in §2 is a **new, separate** service.
- `hotspot_map.html` is a **static artifact** — coordinates baked in at generation
  time. It is the thing the judges loved, and it stays exactly as it is. §2
  explains how it becomes live without being rewritten.

### ⚠️ Flag before anything else

`hotspot_pipeline/Gradhack_Insure_Data.xlsx` — 1.1 MB of raw Discovery claims
data — **is committed and tracked in the public BEACON repo.** `.gitignore` only
covers `data/raw/*.xlsx`, which does not match this path. Verified with
`git ls-files`.

That is Discovery's data on a public GitHub repo. This is a decision for you, not
me, but the options are: (a) leave it, if Discovery supplied it for open hackathon
use; (b) `git rm --cached` + gitignore it, which removes it going forward but not
from history; (c) rewrite history / re-init the repo, which removes it properly.
**Tell me which and I'll do it.** I have not touched it.

---

## 1. The two surfaces, and the routing model

Today `App.tsx` is a client-side tab switcher — five screens behind five buttons,
no URLs, no router. That is fine for a scaffold and wrong for a demo you have to
drive live in five minutes and for a product story about two different users.

**Split into two surfaces, one codebase:**

```
/  ────────────────────────────  Member app   (Sarah/Thabang — the customer)
   /home                         Today's safety picture, Vitality points
   /drive                        Live dashcam view + detections      → Scene 1
   /map                          Hotspot map, filters, suburb detail → Scene 2
   /route                        Destination in → safest route out   → Scene 3
   /home-guard                   Property audio monitoring           → Scene 4
   /assistant                    Beacon Assistant (chat)
   /rewards                      Vitality points ledger

/ops ──────────────────────────  Operations console (Discovery / security)
   /ops/feed                     Live sighting feed
   /ops/verify                   Human verify queue (candidate → flagged)
   /ops/intel                    Crime intelligence, community trends → Scene 5
   /ops/patrol                   OR-Tools patrol planner
   /ops/cameras                  Camera estate health
```

Adopt **`react-router-dom` v7** with `createBrowserRouter`. Concretely this buys
three things you need on the day:

1. **Deep-linkable demo.** Every scene is a URL. If a click misses live, you type
   the URL. If the laptop reboots, you're back in three seconds.
2. **The story reads itself.** `/` is a customer. `/ops` is Discovery. Judges see
   two products' worth of value from one build without you narrating it.
3. **Back button works.** Scene 2 → Scene 3 → back to the map is a real
   navigation, not lost state.

Add `vite.config.ts` → `server.historyApiFallback` (Vite handles this by default
for SPA) and an Azure Static Web Apps `staticwebapp.config.json` rewrite so deep
links survive deployment.

---

## 2. The hotspot map — method preserved, made live

You said: *"i want the map as is in the system the way it is and the method... but
now it needs to also be live like on google maps to give you the safest route."*

Those are two different jobs. Keep them separate so neither damages the other.

### 2.1 The map itself — preserved, not rewritten

`hotspot_map.html` is Leaflet + OSM tiles + baked circle markers. We do **not**
port it to MapLibre or Deck.gl and we do **not** regenerate it by hand.

**In-app: `/map` renders a React Leaflet map with identical visual rules.**
Same `L.circleMarker`, same colour cuts (`≥0.66` `#c0392b`, `≥0.33` `#e67e22`,
else `#f1c40f`), same `radius = 6 + severity × 20`, same popup fields, same
legend, same OSM tiles. The only change: markers come from
`GET /v1/hotspots/geo` (live from the DB) instead of being baked into the HTML.
Judges who saw the static map see the same map — because the rules are copied
verbatim out of `build_hotspots.py::build_map_html`.

**`hotspot_map.html` stays in the repo, untouched, and stays runnable.** It is the
provenance artifact: "here is the standalone map we showed you, here is the same
map live in the product." If the app fails on the day, you double-click the HTML
and the map still works. That is your fallback, for free.

New endpoint (thin — the data is already in the DB):

```
GET /v1/hotspots/geo?hour=17&day=Friday&peril=Hijack&min_severity=0.3
→ { generated_at, count, hotspots: [{
      suburb, lat, lng, severity_score, incident_count,
      top_claim_type, peak_hour, peak_day_of_week, peak_month,
      total_claim_cost, avg_claim_cost, source: "ndu-hotspot-v1" }] }
```

Filters are the Scene 2 story made interactive: *set the hour to 17:00 and the
day to Friday, and watch which suburbs light up.* That is the same insight the
static map delivers in a popup, but as a live query — and it is the exact moment
Sarah realises she is entering a Friday-evening hijack corridor.

### 2.2 Safest route — the new part, and how it honestly works

This is the piece that does not exist yet. The method:

**Step 1 — real road routes with real alternatives.**
Call **OpenRouteService** `POST /v2/directions/driving-car/geojson` with
`alternative_routes: { target_count: 3, share_factor: 0.6, weight_factor: 1.6 }`.
ORS is free, needs only an API key (no card), and — critically — returns genuine
*alternative* road geometries, which Google's free tier and OSRM's demo server do
not reliably give. Fallback if ORS is down: Mapbox Directions `alternatives=true`.

Why not compute routes ourselves: we do not have a road network. `planner.py`
already documents this honestly — it uses haversine because standing up OSRM
mid-hackathon was not worth blocking on. Same call here, different fix: use a
routing API rather than fake a road graph.

**Step 2 — score each route's exposure against Ndu's hotspots.**
This is ours, and it is the defensible bit:

```
for each alternative route:
    sample the polyline every 250 m           → ~120 points on a 30 km route
    for each sample point p, with ETA hour h_p (from ORS per-segment duration):
        find hotspots within 2 km             → scipy.spatial.cKDTree on
                                                 projected (EPSG:3857) coords
        for each nearby hotspot H at distance d:
            w_dist = exp(-d / 800m)              distance decay
            w_hour = 1.6 if H.peak_hour == h_p (±1) else 1.0
            w_day  = 1.4 if H.peak_day_of_week == trip_day else 1.0
            exposure += H.severity_score × w_dist × w_hour × w_day
    normalise by route length → exposure_per_km
```

Then rank: the recommended route is the one minimising
`exposure_per_km`, subject to `duration ≤ 1.25 × fastest_duration` — i.e. **we
will not send someone 40 minutes out of their way**, and we say so on screen.

**Step 3 — the advice text, generated from the data, not written by hand.**
The scorer already knows *which* named suburbs drove the exposure. So:

> **Route via N1** — 22 min, 12% longer than fastest
> Passes within 1.1 km of **BRYANSTON** (89 claims, mostly Theft, peaks Fridays
> around 12:00) and **SANDTON**. Arrives 17:40 — inside the local peak window.
>
> **Recommended: route via William Nicol** — 24 min
> 61% lower hotspot exposure. No high-severity suburb within 2 km.
> **+150 Vitality Points** for taking the safer route.

Every number in that block traces to a real row in `hotspots_geocoded.csv`. Nothing
is invented.

**Honesty boundary — state this before a judge asks:**
Geocoding is **one point per suburb**, from Nominatim, matched on
`"<suburb>, South Africa"` with no province. So this is *proximity to the
geocoded centre of a suburb with a claims history*, **not** a street-level crime
prediction. The API labels it that way (`"method": "suburb_centroid_proximity"`,
`"not_street_level": true`) and the UI says "near areas with recurring claims,"
never "this street is dangerous." Owning this limitation out loud is worth more
than papering over it — it is exactly the kind of thing a Discovery data person
will probe.

New endpoint:

```
POST /v1/routes/safest
  { origin: {lat,lng}, destination_text | destination: {lat,lng},
    depart_at: ISO8601 }
→ { routes: [{ geometry, distance_km, duration_min, exposure_per_km,
               exposure_rank, near_hotspots: [{suburb, min_distance_m,
               severity_score, incident_count, top_claim_type,
               peak_hour, peak_day_of_week}],
               advice: string, vitality_points: int }],
    recommended_index, method: "suburb_centroid_proximity",
    detour_cap_applied: bool }
```

Geocode the destination text with Nominatim — **the same geocoder Ndu used**, so
the destination and the hotspots live in one coordinate frame. Reuse
`geocode_cache.json`'s pattern (cache every lookup, respect 1 req/sec).

**Do not** put this in `planner.py`. New module: `server/src/routing/safest.py`.
The patrol planner maximises risk coverage; this minimises risk exposure. Same
data, opposite objective — sharing a file would confuse both.

---

## 3. Cloud + live database

The judges asked directly. Here is the answer, with the reasoning they'll want.

### Recommendation: **Azure**

Not because Azure is technically superior to GCP here — for this workload they're
close. Because:

1. **You already know it**, and there is an accepted ADR (VUKA ADR-0015) choosing
   Azure. Consistency across your two projects is a coherent story, not an
   accident.
2. **Discovery is a Microsoft shop.** Discovery Limited runs on Azure and Microsoft
   enterprise tooling. A solution that lands inside their existing tenancy,
   compliance posture and EA discount is a solution they can actually adopt.
   That is a *business* answer to a *technical* question, and it is the better
   answer.
3. **POPIA and data residency.** Azure has two South African regions —
   **South Africa North (Johannesburg)** and **South Africa West (Cape Town)**.
   Claims data and member location traces stay in-country by default. GCP has no
   South African region; the nearest is `africa-south1` (Johannesburg) which
   Google opened more recently and has thinner service coverage. For a product
   handling insurance claims plus real-time location, in-country residency isn't a
   nice-to-have — it's the first question a Discovery risk officer asks.

Say this out loud in the pitch. "We chose Azure because Discovery is already on
Azure, and because South Africa North keeps claims and location data inside the
country under POPIA" is a far stronger answer than a feature comparison.

### The architecture

| Concern | Service | Why this one |
|---|---|---|
| **Database** | **Azure Database for PostgreSQL — Flexible Server** + **PostGIS** | PostGIS is the whole reason. Hotspot proximity, route corridor intersection, "which hotspots within 2 km of this polyline" are native `ST_DWithin` / `GIST` index queries instead of Python loops. Also: we're already on SQLAlchemy + SQLite, so this is a connection-string change, not a rewrite |
| **Member app + ops console** | **Azure Static Web Apps** | Free tier, global CDN, built-in GitHub Actions deploy, and `staticwebapp.config.json` handles the SPA deep-link rewrites §1 needs |
| **API + WebSocket** | **Azure Container Apps** | FastAPI in a container, scales 0→N on HTTP concurrency, native WebSocket support. Cheaper and simpler than AKS; unlike Functions, it holds long-lived WS connections properly |
| **Vision microservices** (plate `:8001`, weapon `:8002`) | **Azure Container Apps**, separate revisions, scale-to-zero | They're already FastAPI containers behind HTTP. Scale-to-zero means they cost ~nothing between demos and cold-start only when a frame arrives |
| **Video clips + evidence** | **Azure Blob Storage**, private, SAS-token reads | Clips never in the DB, never in git. Immutability policy on the evidence container = tamper-evidence with a service-level guarantee, not just our hash chain |
| **Scraper + nightly re-scoring** | **Azure Container Apps Jobs** (cron) | Same container image as the API, scheduled. No second runtime to maintain |
| **Push notifications** | **Azure Notification Hubs** | One API to FCM (Android) and APNs. §4 needs this |
| **LLM** | **Azure OpenAI** in South Africa North / **Azure AI Foundry** | Keeps prompts containing member location and claims context inside the same tenancy and region as the data. §5 depends on this |
| **Secrets** | **Azure Key Vault** + Container Apps managed identity | No keys in the repo — which matters, because the repo is public |
| **Realtime fan-out at scale** | **Azure Web PubSub** (post-demo) | Container Apps WS is fine to a few thousand concurrent. Web PubSub is the documented next step; name it, don't build it |

### The scalability answer

Have this ready verbatim, because it's the follow-up question:

> The load isn't uniform, so we don't scale it uniformly. Three tiers:
>
> **Hot path — detections.** A dashcam frame every second per active drive. This
> is the only thing that scales with *concurrent users*. It's stateless HTTP into
> Container Apps, which scales on concurrency, and the vision models are separate
> revisions that scale independently — weapon detection is heavier than plate
> reading, so they shouldn't share a scaling unit.
>
> **Warm path — risk and routing.** Route requests scale with *trips*, not
> seconds. Hotspot geometry changes when the claims data changes — which is
> monthly, not per-request. So hotspots are cached in Redis and the corridor
> scoring runs against an in-memory spatial index. A route request is a routing
> API call plus a KD-tree lookup; it does not touch Postgres on the hot path.
>
> **Cold path — the claims pipeline.** 15,712 claims re-aggregate in under a
> minute. That's a nightly Container Apps Job, not a service. It doesn't need to
> scale at all.
>
> The expensive thing is video, and we never store or move raw video on the hot
> path — we send detections, which are a few hundred bytes. That's a design
> choice for privacy that happens to be the reason this scales.

**Live for the demo.** Deploy the API + DB to Azure and point the demo at it — so
"is this live?" is answered by showing the Azure portal, not by claiming it. Keep
the local stack running as a hot fallback and *say* that's what you're doing if
you switch. Judges forgive a fallback; they don't forgive being misled.

---

## 4. Proactive notifications

The trigger engine has four sources. All four already have real data behind them
or get it in §6.

| # | Trigger | Data source | Example |
|---|---|---|---|
| 1 | **Geofence entry** | 709 geocoded hotspots, 2 km radius, severity-gated | "You're entering **BRYANSTON**. 89 claims on record, mostly theft, peaking Fridays around midday." |
| 2 | **Time + place** | `peak_hour`, `peak_day_of_week` per suburb | Friday 16:30, home is in a Friday-evening hijack suburb: "Hijack claims here peak in the next two hours. Leaving now avoids the window." |
| 3 | **Weather + load-shedding** | Scraper (§6) | "Stage 4 load-shedding in your area 18:00–20:30. Street lighting will be out on your usual route." |
| 4 | **Behavioural** | Member's own trip history | "You've driven through three high-exposure suburbs this week. A route change saves ~40% exposure — and 450 Vitality Points." |

**The rule that makes this a product instead of spam:** every notification must
name a real number from the claims data and be actionable in one tap. If we can't
cite a count, a peak hour, or a severity score, we don't send it. Hard cap: **3
per day**, with a quiet-hours window, and a per-suburb cooldown so the same
geofence can't fire twice in 24 h.

Implementation: `server/src/notify/triggers.py`, evaluated on location ping
(member app posts a coarse location every 5 min while driving) plus a scheduled
job for the time-based ones. Fan-out via Azure Notification Hubs. Every fired
notification is logged with the trigger id and the data that justified it — so
"why did I get this?" is answerable, and so is "why didn't I?"

---

## 5. LLM orchestration + where an agent belongs

You described three roles. Here's the concrete shape.

### The three roles

**① Beacon Assistant — the conversational LLM (safety-ruled).**
Model: `gpt-4.1` or `claude-sonnet` via Azure AI Foundry. Its system prompt carries
the safety contract, and these rules are non-negotiable:

- Never claim an identification. The vision pipeline detects faces; it does not
  match identities. Mirrors `server/src/suspicion/scorer.py` — the machine can
  only reach `"candidate"`, never `"flagged"`; only a human verify call promotes
  it (ADR-0002).
- Never state a risk figure that didn't come from a tool call. No invented
  percentages, no "94% safe."
- Never tell a member to confront, follow, or record a person.
- In an active-emergency turn, stop conversing: surface the emergency actions
  (call 10111, alert contacts, share location) and shut up.
- Always name the limitation when asked "how do you know?" — suburb-level claims
  history, not street-level prediction.

**② The data-fetching layer — tool calls, not a second chat model.**
You described "another that fetches the data from the prompt and the data." The
right implementation is **tool/function calling**, not a second conversational
model. It's cheaper, faster, and — the reason that matters here — it's
*auditable*: every answer traces to a tool call with arguments you can print.

Tools exposed:
```
get_hotspot(suburb)              → the real row from hotspots_geocoded.csv
get_risk(lat, lng, hour)         → /v1/risk, with its honesty label passed through
plan_safest_route(dest, time)    → /v1/routes/safest
get_my_trips(window)             → member's own history
get_local_conditions(area)       → weather + load-shedding (§6)
get_recent_incidents(suburb)     → community reports
```

The assistant cannot state a fact about risk without one of these returning it.
That constraint is the product.

**③ The memory writer — with the yes/no gate you asked for.**
A small classifier pass over each turn: *did the member state a durable fact about
their safety context?* (home suburb, commute pattern, work hours, vehicle,
children's school run, a named place they visit often).

If yes → the assistant **asks for consent in the conversation**:

> "Want me to remember that you usually leave work around 17:30? I'll use it to
> warn you before Friday peak hours. **[Yes] [No]**"

Only on an explicit **Yes** does it write to `member_profile_facts`
(`fact_type`, `value`, `source_message_id`, `consented_at`, `expires_at`).
Nothing is written silently. This is POPIA consent-by-design, and it's a genuinely
good demo beat — the moment the judges see the app *ask permission* is the moment
it stops looking like a hackathon toy.

### Where a real agent belongs

Not in the chat. Chat is a request/response tool-caller — calling that an "agent"
is the thing every other team will do and every sharp judge will see through.

**The real agent is the Overnight Intelligence Agent.** A scheduled Container Apps
Job that runs multi-step, unsupervised, with a goal rather than a prompt:

```
Goal: keep BEACON's picture of risk current, and tell people what changed.

  1. Pull last 24 h: new sightings, verified incidents, scraped news, weather,
     load-shedding schedule
  2. For each suburb with new signal, re-run the aggregation and diff against
     yesterday's severity_score
  3. Where a suburb moved materially, decide WHY — new incident cluster? a news
     event? a schedule change? — and write a short justified note
  4. Draft tomorrow's proactive notifications for members whose routes or home
     suburb intersect a changed area
  5. Draft the ops console morning briefing
  6. Anything that would change a member-visible risk score by more than a
     threshold → queue for HUMAN APPROVAL, don't ship it
```

That's an agent: a goal, multiple tools, a loop, its own decisions about what
matters — and a human gate on the consequential ones. Step 6 is the part that
makes it defensible rather than reckless, and it's the same human-in-the-loop
principle as the verify queue, applied to the intelligence layer.

**Demo it by showing yesterday's output**, not by running it live. "This ran at
3am. Here's what it noticed and here's what it queued for a human." Much stronger
than watching a spinner.

---

## 6. The news + weather scraper

`server/src/ingest/`, three sources, all run as scheduled Container Apps Jobs:

| Source | How | Cadence | Feeds |
|---|---|---|---|
| **Weather** | WeatherAPI.com free tier (you already hold a key for VUKA) | hourly | Notifications, route advice ("heavy rain + peak hour on this route") |
| **Load-shedding** | EskomSePush API (key already held) | 30 min | Notifications, and a real context signal — dark suburb + peak hour |
| **News** | RSS-first: News24, IOL, EWN, SAPS media releases. `feedparser` + `httpx`. Full-article fetch only for matched items, via `trafilatura` | 15 min | Chatbot context, hotspot corroboration |

**Scrape politely and say so:** RSS where offered (all four offer it), `robots.txt`
respected via `urllib.robotparser`, a real identifying User-Agent, rate-limited —
the same discipline `build_hotspots.py` already applies to Nominatim's 1 req/sec
policy. Store **links, headlines and extracted entities — never full article
text.** That is both a copyright position and a storage decision, and it's the
honest one.

Pipeline for a matched article:
```
RSS item → keyword gate (hijack|robbery|smash-and-grab|burglary|carjacking)
         → suburb extraction (match against the 764 known suburb names — we
           already have the gazetteer, no NER model needed)
         → geocode via the existing Nominatim cache
         → write ScrapedIncident{source_url, headline, suburb, hex_id,
                                 incident_type, published_at, confidence}
```

**Critical honesty rule: scraped news never modifies `severity_score`.** Ndu's
score comes from 15,712 verified claims. A news headline is unverified, and
mixing them would quietly corrupt a defensible number with an undefensible one.
News surfaces as a **separate, clearly-labelled layer** — "3 reported incidents
in the news this week (unverified)" next to "89 claims on record (Discovery
data)". Two sources, two labels, never merged. If a judge asks whether news
inflates the risk scores, the answer is a flat no, by construction.

---

## 7. THE UI DESIGN PROMPT

*Copy everything between the rules into Claude Design.*

---

**Design a mobile-first product called BEACON — a proactive safety companion built
on Discovery Insure's real claims data. Two surfaces in one design system: a
consumer member app (primary) and an operations console (secondary).**

**Brand & tone.** Discovery's institutional credibility, not a startup safety app.
Calm, precise, evidence-led. This app shows people risk data about where they
live — alarmist design would be irresponsible and would undermine trust. Confident
and quiet. Never red-alert-everything.

**Design tokens (use exactly — these are live in code as Tailwind v4 `@theme`):**

```
Dark chrome:   bg-900 #0A0F1A · bg-800 #101725 · bg-700 #182130
               text-hi #F1F5F9 · text-mid #94A3B8 · text-lo #64748B
               line-dark rgba(255,255,255,0.08)
Light content: bg-50 #F7F9FC · bg-0 #FFFFFF
               ink-hi #0F172A · ink-mid #475569 · ink-lo #94A3B8
               line-light rgba(15,23,42,0.08)
Brand:         beacon #F5A623 → beacon-deep #F27B21 (gradient 135°)
               discovery #0B5FA5 · discovery-soft #E8F1F9
Risk ramp:     safe #10B981 · watch #F59E0B · high #F0653A · critical #E11D48
               (RISK/SEVERITY ONLY — never decorative)
Semantic:      live #22D3EE · stale #6B7280
Elevation:     card       0 1px 2px rgba(15,23,42,.06), 0 6px 20px rgba(15,23,42,.06)
               card-dark  0 1px 2px rgba(0,0,0,.3),     0 8px 28px rgba(0,0,0,.35)
Type:          Inter Variable. Tabular figures on every live-updating number.
```

**Shape & motion language:**
- Corner radii: 12 px inputs/chips · 16 px cards · 20 px sheets · 28 px primary
  buttons (pill) · 32 px phone frame
- Buttons: pill-shaped, generous (min 48 px tall, 44 px minimum touch target),
  gradient fill on primary, soft shadow, `translateY(-1px)` + `brightness(1.08)`
  on hover, `translateY(0)` + `brightness(0.95)` on press, 120 ms ease
- Motion: 120–200 ms for state, 260–320 ms for sheets and route transitions.
  Spring only on the map. Nothing bounces on an alert — alerts appear decisively
  and stay still
- Generous whitespace. 8 px spacing grid. Cards breathe: 20–24 px internal padding
- Soft elevation over hard borders, everywhere

**Screens to design (member app — light theme, `bg-50` background):**

**1 · `/home` — Today**
Greeting + current safety picture. A "Today's risk" card: the member's home
suburb, its severity band as a coloured ring (risk ramp), incident count, peak
window. Below: next trip card with a one-tap "Plan safest route." Vitality Points
balance with this week's safety-earned points. Recent alerts list, max 3. An empty
state that reads calm, not broken.

**2 · `/drive` — Live drive (Scene 1)**
The hero screen. A circular "lens" viewport (the dashcam feed) with detection
bounding boxes overlaid, on `bg-900` dark chrome. Below the lens: a live detection
strip. Beside/below it, a phone-lock-screen mockup showing what the member
actually receives — a single notification card, not raw AI output.
**Copy discipline, non-negotiable:** a weapon detection reads "Potential weapon
detected"; a face detection reads "**Possible match — flagged for review**",
never "high-risk individual identified" — the system detects faces, it does not
identify people, and only a human can promote a candidate. An unread plate reads
"Plate seen, not read — below the confidence gate." Design the honest states as
first-class, not as errors.

**3 · `/map` — Hotspot map (Scene 2)**
Full-bleed Leaflet map, OSM tiles. Circle markers: red `#c0392b` (severity ≥0.66),
orange `#e67e22` (≥0.33), yellow `#f1c40f` below; radius scales 6→26 px with
severity. **These exact colours and rules are inherited from an existing map the
client already approved — do not restyle them.** Design the *chrome* around it:
a floating filter bar (hour scrubber, day-of-week pills, claim-type chips, severity
slider), a bottom sheet that slides up on marker tap showing suburb detail
(incidents, top claim type, peak day/hour/month, total & average claim cost,
severity), and a persistent "15,712 Discovery claims analysed · 709 suburbs
mapped" provenance line. The hour scrubber is the money interaction — dragging it
to 17:00 on a Friday should visibly change the map.

**4 · `/route` — Safest route (Scene 3)**
Google-Maps-familiar, deliberately. Destination search field pinned top. Map with
2–3 alternative route polylines: recommended route in `safe #10B981`, alternatives
in `ink-lo`, and high-risk corridor segments in `high #F0653A`. A bottom sheet
comparing routes as cards — each showing duration, distance, an **exposure bar**
(the risk ramp), and a plain-language line: "passes within 1.1 km of BRYANSTON —
89 claims, peaks Fridays around 12:00." The recommended card carries a
`+150 Vitality Points` badge in the beacon gradient. One primary pill button:
"Start safer route." Include the honesty line in the sheet: "Based on suburb-level
claims history, not street-level prediction."

**5 · `/home-guard` — Property monitoring (Scene 4)**
Calm, mostly-idle screen — this is a state people look at when nothing is wrong.
Property card, monitoring status with a live pulse dot (`live #22D3EE`), an audio
waveform visual, and the classes being listened for (glass breaking, raised voices,
distress). Then design the **active detection state**: a decisive but non-panicking
alert sheet — "We detected the sound of breaking glass at your property. Are you
home?" with two large pill buttons `[I'm home]` `[I'm not home]`, and an escalation
timer with a visible cancel. Design the escalation ladder that follows the "not
home" answer.

**6 · `/assistant` — Beacon Assistant**
Clean chat. Assistant messages on `bg-0` cards with soft elevation; member messages
in `discovery-soft`. **Design two things most chat UIs skip:** (a) a *data
citation chip* under any message containing a figure — "from 89 claims in
BRYANSTON" — tappable through to the map; (b) the **consent card**, an inline
prompt with `[Yes] [No]` pill buttons: "Want me to remember that you usually leave
work around 17:30?" This card is a signature moment — make it feel considerate,
not like a cookie banner.

**7 · `/rewards` — Vitality Points**
Points balance as the hero. A ledger of safety-earned points ("Took the safer
route via William Nicol — +150"). Progress toward the next tier. This screen makes
the business case visible: Discovery pays people to avoid becoming claims.

**Screens to design (ops console — dark theme, `bg-900` chrome):**

**8 · `/ops/feed`** — dense live sighting feed, virtualised list, severity-coded
left rails, live/stale indicators. Operator-grade density: this screen is allowed
to be information-dense in a way the member app must never be.

**9 · `/ops/verify`** — the human-in-the-loop queue. Side-by-side: the detection
evidence and the decision controls. Prominent, unambiguous `[Confirm] [Reject]`.
Make it visually obvious that **a machine cannot do this** — the promotion from
"candidate" to "flagged" is a human act, and the design should say so.

**10 · `/ops/intel` (Scene 5)** — community intelligence. Trend charts, emerging
hotspots ranked by *change* not absolute severity, repeat-entity tracking, and the
overnight agent's morning briefing card with its human-approval queue.

**Navigation:** member app gets a bottom tab bar (Home · Drive · Map · Assistant ·
Rewards) — thumb-reachable, 5 items max, with the active item in the beacon
gradient. Ops console gets a dark top bar with nav pills. The two surfaces must
feel like one family and never be mistaken for each other.

**States to design for every screen — these are not optional:**
loading (skeletons, never spinners on data screens) · empty · error · **stale data
(explicitly marked, never silently blank)** · offline. Stale-vs-live is a core
part of this product's honesty and must be visible in the design.

**Accessibility:** WCAG AA contrast minimum. Risk is never encoded by colour alone
— always colour + label + shape. Every touch target ≥44 px. Design in both light
and dark where the surface supports it.

**Explicitly do NOT design:** anything that claims identification of a person,
any uncalibrated percentage presented as precision, any "100% safe" or
"guaranteed" language, or a panic-red interface. This product's credibility is its
differentiator.

---

## 8. Demo run-of-show (5 minutes)

| Time | Scene | Screen | The line that lands |
|---|---|---|---|
| 0:00 | Hook | `/home` | "Discovery pays 15,712 of these claims. We asked: what if we stopped some of them?" |
| 0:30 | **1** | `/drive` | Play the hijack clip. Weapon box appears. Phone mockup fires the alert **at the same instant**. "That's a real detection on real footage — not a mock-up." |
| 1:20 | **2** | `/map` | Drag the hour scrubber to 17:00, tap Friday. The map changes. "This is every suburb in Discovery's claims data. 709 of them geocoded." |
| 2:10 | **3** | `/route` | Type a destination. Three routes appear. "Two minutes longer, 61% less exposure — and Discovery pays her 150 Vitality Points to take it." |
| 3:10 | **4** | `/home-guard` | Trigger the glass-break state. "Are you home?" → escalation. "Same platform, different sensor." |
| 3:50 | **5** | `/ops/verify` → `/ops/intel` | Show the verify queue. "The machine says *candidate*. Only a human says *flagged*. That's a design decision, and it's why this is deployable." Then the overnight agent's briefing. |
| 4:30 | Close | Azure portal | "It's live, it's in South Africa North, and here's what it costs to run." |

**Fallbacks, prepared, not improvised:** every scene is a URL (§1). The static
`hotspot_map.html` opens standalone if `/map` fails. A recorded screen capture of
the full run sits on the desktop. If you switch to a fallback, **say so** — CLAUDE
principle 8: judges forgive simulation, they don't forgive being misled.

---

## 9. "How did you do that" — the answers

Have these ready. Each is a real answer with a real artifact behind it.

**"How did you get the crime data?"**
Discovery's own 15,712 claims. Cleaned with an auditable script — 196 rows
backfilled, 651 missing suburbs flagged not deleted, 81 anomalous amounts excluded
from cost but kept in frequency. Every fix is a flag column you can filter on.

**"How are the hotspots ranked?"**
Composite severity: normalised incident frequency and normalised total claim cost,
50/50. That's a deliberate choice, not a fitted parameter, and it's adjustable —
weight cost higher if the priority is preventing expensive losses, frequency
higher if it's patrol coverage. It's why Bryanston (89 incidents, high value)
outranks Johannesburg (110 incidents, lower value).

**"Why only 764 suburbs when the data has 2,929?"**
5-incident minimum. Below that you're mapping coincidence, not a pattern. 764
suburbs cover ~75% of usable claims. 709 of them geocoded successfully.

**"How does the safest route actually work?"**
Real road alternatives from OpenRouteService, then each route's polyline is
sampled every 250 m and scored against the geocoded hotspots with a distance
decay, an hour-of-arrival weight and a day-of-week weight — using each suburb's
*own* peak hour and peak day from the claims data. Ranked by exposure per km,
capped so we never send you 25% further out of your way.

**"How accurate is the plate reading?"**
We don't claim an accuracy figure, because we haven't measured one on South
African plates. What we do instead: if character confidence is below the gate,
the system records "plate seen, not read" rather than guessing. In our demo clip
15 plates were detected and **zero** were read. That's the honest result, and
showing it is the point — a read is a lead, never an identification.

**"Is the face recognition identifying people?"**
No. It detects that a face is present. It does not match against a watchlist.
The scoring engine cannot set anything to "flagged" — only "observed" or
"candidate". Promotion requires a human verify action. That's enforced in code,
not policy.

**"What cloud, and why?"** → §3.

### The honesty ledger — claims we refuse to make

- ❌ "Predicts crime" → ✅ identifies where claims recurred, and when
- ❌ "Street-level risk" → ✅ suburb-level, one geocoded point per suburb
- ❌ "Identifies criminals" → ✅ detects faces; humans identify
- ❌ "X% accurate" → ✅ no accuracy claim without a measurement
- ❌ "Court-admissible evidence" → ✅ structured to support a case
- ❌ "Guarantees your safety" → ✅ reduces exposure to areas with claims history

This list is the moat. Every other team will overclaim. Being the one team that
draws the line — and can show it enforced in code — is what a Discovery risk
officer remembers.

---

## 10. Build order

| # | Slice | Blocks |
|---|---|---|
| 1 | ~~Tailwind v4 `@theme`~~ ✅ done — utilities verified generating | Design handoff |
| 2 | `react-router-dom`, split `/` and `/ops`, move existing screens onto routes | Everything |
| 3 | `GET /v1/hotspots/geo` + `/map` in React Leaflet, rules copied from `build_hotspots.py` | Scene 2 |
| 4 | `server/src/routing/safest.py` + `POST /v1/routes/safest` + ORS key | Scene 3 |
| 5 | Claude Design → Claude Code: skin every screen with §7 | The wow |
| 6 | Azure deploy: Postgres+PostGIS, Container Apps, Static Web Apps | The live claim |
| 7 | Assistant + tool calls + consent card | §5 |
| 8 | Scraper jobs | §6 |
| 9 | Overnight agent + morning briefing | §5, Scene 5 |
| 10 | `/home-guard` audio | Scene 4 |

Items 2–4 are the ones that must be real before the design handoff, because the
design needs real screens to attach to. 5 is the visual leap. 6 is the sentence
"it's live." Everything after is depth.

---

## Open decisions for Lethabo

1. **`Gradhack_Insure_Data.xlsx` in the public repo** — leave, untrack, or purge
   from history? (§0)
2. **Azure confirmed?** If yes I'll write the ADR and the Bicep/`azd` scaffold.
3. **OpenRouteService API key** — free, no card, you create it (I never handle
   keys). Needed for §2.2.
4. **Scene 4 (home audio)** — build for real, or design-only and simulated with a
   labelled `sim_` prefix? Real Whisper-based audio classification is the largest
   remaining unbuilt piece.
5. **Third demo clip** — the `DEMO_CLIPS` array in `RingCam.tsx` has the slot
   ready.
