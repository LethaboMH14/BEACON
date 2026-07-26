"""
EskomSePush data pipeline for VUKA context_signals table.

WHAT THIS DOES
--------------
1. One-time: searches for your area by name, gets its area ID, saves it to a
   local config file so you never have to search again.
2. On a schedule (every N minutes): pulls
     - official load-shedding status for your area (`area` endpoint)
     - national load-shedding status (`status` endpoint)
     - nearby user-reported "topics" (`topics_nearby` endpoint) — this is the
       closest CONFIRMED endpoint to "community-reported outages". See the
       IMPORTANT NOTE below before you trust its field names.
3. Appends everything into a local SQLite database, in a normalized
   `context_signals` table: (area_cell, timestamp, signal_type, value).

IMPORTANT NOTE — READ BEFORE RELYING ON THIS
---------------------------------------------
I could only confirm the EXISTENCE of `topics_nearby` (user-generated topics
by GPS location) in the public docs — not its exact JSON shape, and not a
claim of "10M+ users / live counts per municipality / electricity-water-
internet breakdown". That specific framing wasn't in anything I could verify.

The FIRST time you run this script, it will print the raw JSON from
`topics_nearby` to your terminal. Look at it yourself, see what fields it
actually contains (e.g. does it have a "type" field distinguishing outage
categories? a free-text description? a municipality name?), and then adjust
the `parse_topics()` function below to match reality. Don't trust the
placeholder parsing logic as correct until you've seen real output.

SETUP
-----
1. Get a free token: https://eskomsepush.gumroad.com/l/api  (enter R0/$0)
2. pip3 install requests
3. Edit the CONFIG section below (your token, area search text, lat/lng)
4. Run once to initialize:  python3 esp_pipeline.py --once
5. Run on a schedule (see "WHERE TO PUT THIS" instructions sent separately)
"""

import requests
import sqlite3
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

# ============================================================
# CONFIG — edit these before running
# ============================================================
ESP_TOKEN = "002A3991-1CBD4CE2-BA2F5E83-69E0F2C4"          # from eskomsepush.gumroad.com/l/api
AREA_SEARCH_TEXT = "sandton"           # suburb/area name to search for once
PREFERRED_PROVINCE = "Gauteng"         # used to disambiguate multiple matches (e.g. several towns share a name)
PREFERRED_MUNICIPALITY = "City of Johannesburg"  # set to None to skip this filter
AREA_LAT = -26.107                     # used for topics_nearby (GPS-based)
AREA_LNG = 28.056
POLL_INTERVAL_MINUTES = 60             # how often to pull data when running continuously

BASE_URL = "https://developer.sepush.co.za/business/3.0"  # v2.0 confirmed retired (410 Gone) as of 2026-07; using v3.0
CONFIG_FILE = Path("esp_config.json")   # stores the area_id after first lookup
DB_FILE = Path("context_signals.db")

HEADERS = {"token": ESP_TOKEN}


# ============================================================
# STEP 1 — One-time area lookup (cached to esp_config.json)
# ============================================================
def get_or_find_area_id():
    """Load area_id from cache, or search for it once and save it."""
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
        if "area_id" in cfg:
            print(f"Using cached area_id: {cfg['area_id']}")
            return cfg["area_id"]

    print(f"No cached area_id found — searching for '{AREA_SEARCH_TEXT}'...")
    resp = requests.get(
        f"{BASE_URL}/areas_search",
        params={"text": AREA_SEARCH_TEXT},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    print("Raw areas_search response:", json.dumps(data, indent=2))

    areas = data.get("areas", [])
    if not areas:
        raise RuntimeError(
            f"No areas found for '{AREA_SEARCH_TEXT}'. Try a different search term."
        )

    # NOTE: response schema uses "municipality" and "province" fields, not
    # "region" (older docs/community wrappers described an older, different
    # schema — don't trust older sample code's field names blindly).
    print(f"\n{len(areas)} area(s) matched '{AREA_SEARCH_TEXT}':")
    for a in areas:
        muni = a.get("municipality", "unknown municipality")
        prov = a.get("province", "unknown province")
        print(f"  {a['id']}  ->  {a['name']} ({muni}, {prov})")

    # Try to disambiguate using PREFERRED_PROVINCE / PREFERRED_MUNICIPALITY,
    # since a search term like 'sandton' can match unrelated places in other
    # provinces (confirmed: this happened on first run — matched a Limpopo
    # town before the intended Johannesburg suburb).
    candidates = areas
    if PREFERRED_PROVINCE:
        filtered = [a for a in candidates if a.get("province") == PREFERRED_PROVINCE]
        if filtered:
            candidates = filtered
    if PREFERRED_MUNICIPALITY:
        filtered = [a for a in candidates if a.get("municipality") == PREFERRED_MUNICIPALITY]
        if filtered:
            candidates = filtered

    if len(candidates) > 1:
        print("\nStill multiple candidates after filtering — using the first one. "
              "If this is wrong, edit esp_config.json manually with the correct id, "
              "or tighten PREFERRED_PROVINCE/PREFERRED_MUNICIPALITY in CONFIG.")
    elif not candidates:
        print("\nNo areas matched the preferred province/municipality filters — "
              "falling back to the first raw result. Check this is correct.")
        candidates = areas

    chosen = candidates[0]
    area_id = chosen["id"]
    CONFIG_FILE.write_text(json.dumps({
        "area_id": area_id,
        "name": chosen.get("name"),
        "municipality": chosen.get("municipality"),
        "province": chosen.get("province"),
    }, indent=2))
    print(f"Saved area_id '{area_id}' ({chosen.get('name')}, {chosen.get('municipality')}) to {CONFIG_FILE}")
    return area_id


# ============================================================
# STEP 2 — Pull data from each endpoint
# ============================================================
def fetch_area_status(area_id):
    """Official load-shedding schedule/events for the specific area."""
    resp = requests.get(
        f"{BASE_URL}/area", params={"id": area_id}, headers=HEADERS, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def fetch_national_status():
    """National load-shedding stage."""
    resp = requests.get(f"{BASE_URL}/status", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_topics_nearby(lat, lng):
    """
    User-generated 'topics' near a GPS point — the confirmed endpoint closest
    to community-reported issues. Shape of the response is NOT verified here;
    inspect the printed raw JSON on first run.
    """
    resp = requests.get(
        f"{BASE_URL}/topics_nearby",
        params={"lat": lat, "lon": lng},   # NOTE: confirm exact param names
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def check_allowance():
    """Doesn't cost quota — check how many calls you have left today."""
    resp = requests.get(f"{BASE_URL}/api_allowance", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ============================================================
# STEP 3 — Parsing into normalized signals
# ============================================================
def parse_area_status(area_id, raw):
    """
    Turn the area status response into a list of
    (area_cell, timestamp, signal_type, value) tuples.
    ADJUST field names below once you've seen real output from fetch_area_status().
    """
    now = datetime.now(timezone.utc).isoformat()
    signals = []

    events = raw.get("events", [])
    signals.append((area_id, now, "loadshedding_active_events_count", str(len(events))))

    for i, ev in enumerate(events):
        note = ev.get("note", "")
        start = ev.get("start", "")
        end = ev.get("end", "")
        signals.append((area_id, now, f"loadshedding_event_{i}", f"{start}|{end}|{note}"))

    return signals


def parse_national_status(raw):
    now = datetime.now(timezone.utc).isoformat()
    signals = []
    for grid_name, grid_data in raw.get("status", {}).items():
        stage = grid_data.get("stage", "unknown")
        signals.append(("NATIONAL", now, f"loadshedding_stage_{grid_name}", str(stage)))
    return signals


def parse_topics(area_id, raw):
    """
    PLACEHOLDER — you MUST inspect the real JSON from topics_nearby and
    rewrite this to match actual field names. This is a best-guess parse
    based on typical shapes ('topics': [...]) but is NOT verified.
    """
    now = datetime.now(timezone.utc).isoformat()
    signals = []
    topics = raw.get("topics", [])
    signals.append((area_id, now, "community_topics_count", str(len(topics))))
    for i, t in enumerate(topics):
        # Guessed fields — replace 'body'/'title' with whatever keys you
        # actually see printed when you run this the first time.
        text = t.get("body") or t.get("title") or json.dumps(t)
        signals.append((area_id, now, f"community_topic_{i}", str(text)[:500]))
    return signals


# ============================================================
# STEP 4 — Store in SQLite
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS context_signals (
            area_cell   TEXT,
            timestamp   TEXT,
            signal_type TEXT,
            value       TEXT
        )
    """)
    conn.commit()
    return conn


def store_signals(conn, signals):
    conn.executemany(
        "INSERT INTO context_signals (area_cell, timestamp, signal_type, value) VALUES (?, ?, ?, ?)",
        signals,
    )
    conn.commit()


# ============================================================
# MAIN — one poll cycle
# ============================================================
def run_once():
    area_id = get_or_find_area_id()
    conn = init_db()

    allowance = check_allowance()
    print("Current quota allowance:", json.dumps(allowance, indent=2))

    all_signals = []

    print("\nFetching area status...")
    area_raw = fetch_area_status(area_id)
    print("Raw area status response:", json.dumps(area_raw, indent=2)[:2000])
    all_signals.extend(parse_area_status(area_id, area_raw))

    print("\nFetching national status...")
    national_raw = fetch_national_status()
    print("Raw national status response:", json.dumps(national_raw, indent=2)[:2000])
    all_signals.extend(parse_national_status(national_raw))

    print("\nSkipping topics_nearby (community reports) — this endpoint returned a 404 "
          "against the real API on first test and could not be confirmed as a working, "
          "documented feature. See notes at the top of this file. If you later find "
          "documented proof it exists, re-enable the block below.")
    # try:
    #     topics_raw = fetch_topics_nearby(AREA_LAT, AREA_LNG)
    #     print("Raw topics_nearby response:", json.dumps(topics_raw, indent=2)[:2000])
    #     all_signals.extend(parse_topics(area_id, topics_raw))
    # except requests.HTTPError as e:
    #     print(f"topics_nearby call failed ({e}) — skipping for this cycle.")

    store_signals(conn, all_signals)
    print(f"\nStored {len(all_signals)} signal rows in {DB_FILE}")
    conn.close()


def run_forever():
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"Error during poll cycle: {e}")
        print(f"\nSleeping {POLL_INTERVAL_MINUTES} minutes...\n")
        time.sleep(POLL_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single poll cycle and exit")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_forever()
