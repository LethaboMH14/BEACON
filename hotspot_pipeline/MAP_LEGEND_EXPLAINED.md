# Map Legend Explained

A full breakdown of every marker type, color, and legend entry on
`hotspot_map.html`, and exactly how each one is calculated.

---

## The three marker layers

The map deliberately uses **three visually distinct marker types**, not
one, so the map never implies "no marker here = safe" for an area that
simply has no Discovery claims data.

### 1. 🟢 Green-ringed circles — Discovery + SAPS verified

A hot-spot suburb that has **both**:
- Discovery claims data (from `hotspots.csv`)
- A matched, verified SAPS police precinct (from `integrate_saps.py`'s
  `SUBURB_TO_PRECINCT` mapping)

These are your strongest data points — independently confirmed by two
separate sources. Clicking one shows both a blue "Discovery Claims Data"
section and a green "SAPS Official Data" section in the same popup.

### 2. ⚪ Grey-ringed circles — Discovery claims only

A hot-spot suburb with Discovery claims data, but **no SAPS precinct
mapped yet**. This is the majority of markers on the map, because the
suburb ↔ precinct mapping is currently built by hand and only covers a
handful of suburbs so far (see `SUBURB_TO_PRECINCT` in `integrate_saps.py`).

Clicking one shows the blue "Discovery Claims Data" section, and a plain
grey note: *"No SAPS precinct mapping yet for this suburb."*

**Important:** a grey ring does **not** mean SAPS has no data for that
area — it means we haven't yet built the suburb-to-precinct mapping for
it. The underlying SAPS data may well cover it under a different, precinct
-based name.

### 3. 🟦 Blue squares — SAPS-only precincts

Real SAPS police precincts with significant crime activity (10+ incidents
across the tracked categories in Q1 2026) that have **no** corresponding
Discovery hot-spot at all — meaning no Discovery-insured member has filed
a claim there in this dataset.

These are shown as **squares, not circles**, specifically so they are
never visually confused with the Discovery-scored circle markers. Their
severity score is calculated differently (see below), and is **not
directly comparable** to the Discovery severity score.

Clicking one shows only the green "SAPS Official Data" section, with an
explicit note that no Discovery claims data exists for that area.

---

## Why the squares almost went unseen (and how that was fixed)

An earlier build attempt drew the squares using real-world map coordinates
(latitude/longitude offsets), sized in **meters**. At the map's default
zoom level (showing the whole of South Africa), a marker only 13–26 meters
wide works out to roughly **1/100th of a single screen pixel** — present in
the code, mathematically correct, but completely invisible on screen.

The fix: squares are now built using `L.divIcon`, sized in actual **screen
pixels** (12–32px, scaling with severity score) — the same way the circle
markers' radius already works. This means the squares stay a consistent,
visible size on screen no matter how far in or out you zoom, exactly like
the circles do.

---

## Circle color and size — Discovery severity score

Circle **fill color**:

| Color | Severity score range | Meaning |
|---|---|---|
| 🔴 Red | ≥ 0.66 | High severity |
| 🟠 Orange | 0.33 – 0.66 | Medium severity |
| 🟡 Yellow | < 0.33 | Lower severity |

Circle **size** scales directly with the severity score — larger circle =
higher severity.

The Discovery severity score combines two things in equal measure:
1. **How often** incidents happen in that suburb (frequency), scaled 0–1
   across all hot-spot suburbs
2. **How much** those incidents cost in total (`total_claim_cost`), also
   scaled 0–1, using only non-anomalous claim amounts

```
severity_score = 0.5 × frequency_score + 0.5 × cost_score
```

This is why a suburb with fewer but costlier incidents (e.g. Bryanston)
can rank above a higher-volume, lower-cost suburb — the score isn't just
counting incidents, it's weighing their financial severity too.

**Ring color** (border, separate from fill color) shows data source, not
severity — green ring = SAPS-verified, thin grey ring = Discovery only
(see marker layers above).

---

## Square color and size — SAPS-only severity score

Square **fill color**:

| Color | SAPS-only score range | Meaning |
|---|---|---|
| 🔵 Dark blue | ≥ 0.66 | High activity |
| 🔷 Medium blue | 0.33 – 0.66 | Moderate activity |
| 🟦 Light blue | < 0.33 | Lower activity |

Square **size** scales with the SAPS-only severity score, same principle
as the circles.

**This score is calculated differently from the Discovery severity score**,
and this difference matters:

```
saps_only_severity_score = normalized(total_q1_2026_incidents)
```

It's **frequency only** — there is no cost/Rand-value figure on the SAPS
side to combine it with, unlike Discovery's claims data which has an
actual claim amount per incident. Because of this, **a 0.70 SAPS-only
score and a 0.70 Discovery severity score are not measuring the same
thing**, and shouldn't be presented as directly comparable numbers. Every
SAPS-only popup includes a short note reiterating this.

---

## The "Increased / Decreased / Stabilized" trend arrows

Inside a SAPS data section, each crime category shows a small trend
indicator:

- **▲ Increased** — that crime category's Q1 2026 (Jan–Mar) count is
  *higher* than the same Jan–Mar period the previous year (2025), for
  that specific precinct
- **▼ Decreased** — Q1 2026 count is *lower* than Q1 2025 for that
  precinct
- **● Stabilized** — the count is roughly unchanged year-on-year

This value comes directly from SAPS's own `"Count direction"` field in
the raw workbook — it is not calculated by this pipeline.

**Important nuance:** this is a single **year-over-year** comparison
(2026 vs. 2025 only), not a multi-year trend or a forecast. A precinct
could show "Increased" even if its broader five-year pattern is generally
improving, if this one year happened to tick up. The full five-year
monthly breakdown exists in the raw SAPS file (`RAW Data` sheet) if a
longer-term trend view is ever needed.

---

## Data source labeling, at a glance

| In the popup | Means |
|---|---|
| Blue-bordered section, "Discovery Claims Data" | From Discovery's insured members' claims |
| Green-bordered section, "SAPS Official Data" | From official SAPS police statistics, Q1 2026 |
| Grey note, "No SAPS precinct mapping yet" | Discovery data exists; SAPS mapping hasn't been built for this suburb yet |
| Grey note, "No Discovery claims data found" | SAPS data exists; no Discovery claim exists for this precinct at all |

The two data sources are always shown in clearly separated, distinctly
colored sections — never merged into a single blended figure — so it's
always clear which claim is coming from which source.

---

## Known accuracy caveats

- **Suburb-to-precinct mapping is manual and incomplete.** SAPS records
  crime by police precinct (e.g. "Sandton"), not suburb name (e.g.
  "Bryanston"). There's no reliable free public lookup table between the
  two, so `SUBURB_TO_PRECINCT` in `integrate_saps.py` is a hand-built,
  partial dictionary. Most Discovery hot-spots currently show a grey ring
  simply because their precinct hasn't been looked up and added yet — not
  because SAPS has no data for them.
- **Geocoding is name-based only**, matching `"<name>, South Africa"`
  against OpenStreetMap's Nominatim service, without a province filter.
  There's a small chance of matching a same-named place in the wrong
  province. Worth spot-checking prominent markers against their known
  real location before presenting.
- **Only suburbs/precincts above a minimum incident count are shown** —
  5+ incidents for Discovery hot-spots, 10+ for SAPS-only precincts. This
  filters out one-off, statistically unreliable locations, but also means
  genuinely low-incident areas simply don't appear on the map at all,
  which is a deliberate noise-reduction choice, not a data gap.
