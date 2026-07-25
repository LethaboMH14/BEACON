# BEACON — Demo concept menu (creative options, nothing locked)

> Status: **exploratory**, 2026-07-25. Owner: Lethabo. Nothing here supersedes `docs/06-DEMO-PLAN.md` until we pick.
> Purpose: the scripted demo in docs/06 is solid but conventional — detect, escalate, done. Every other team at the
> hackathon will demo "we ran a detector and something turned red." These are the beats that are *ours*, ranked by
> how hard they'd be to steal.

---

## 0. The problem with a pure detection demo

A gun box and a plate box are table stakes — a judge has seen YOLO before, and a detection demo silently invites
the question *"so you fine-tuned a model, what's the product?"* Our actual moat is three things a detector alone
never shows:

1. **Calibrated multi-modal fusion** — evidence that means nothing alone crossing a threshold together (F1–F6).
2. **The machine ceiling** — the system is architecturally incapable of acting alone (ADR-0002).
3. **Working when everything else is down** — offline, load-shedding, stale-but-honest.

Every concept below is chosen to make one of those visible instead of stated on a slide.

---

## 1. The Time Machine (real claim, replayed) — **strongest business beat**

**The beat.** Pull one real claim out of the 15,712-row Discovery dataset: a real vehicle theft, real suburb,
real timestamp, real rand value. Show it on the map as it exists today — a red dot, reactive, hours after the fact.
Then: *"This is what your system saw. Here's what ours would have seen."* Rewind 72 hours and replay the sighting
stream against that exact location — the suspicion score climbing across nights, the near-repeat cordon forming,
the interception hex.

**Why it lands.** It uses the buyer's own money as the counterfactual. Not "crime is bad" — *"this specific claim,
this specific amount, and here is the 40-minute window where it was preventable."* An insurer audience cannot
un-hear that.

**Real vs. built:** claims data is real and loaded (15,712 rows). The replay sighting stream is `sim_` and must be
said out loud. Entity resolution + F1 scoring underneath is real.
**Effort:** medium — needs a replay generator + the timeline UI. **Risk:** low, it's all local, nothing live to fail.

---

## 2. The Fusion Orchestra — **strongest technical beat**

**The beat.** Three signals, each individually boring, arriving over ~40 seconds:
- a car parks and stays (benign — people park)
- YAMNet hears glass break (benign — could be anything, could be a bottle)
- it's 00:14 in a hex flagged for near-repeat contagion (benign — it's just a time and a place)

Show each one land as a factor chip with its own weight, and the fused confidence meter step up **without crossing
the threshold**. Then the third arrives and it crosses. *"No single one of those is worth waking anyone up for.
That's why alarm systems cry wolf. Ours only speaks when independent evidence agrees."*

**Why it lands.** This is the one thing on stage that a competitor cannot reproduce by downloading a model. It shows
the maths is doing work. It also sets up the honesty story — you can visibly show the meter *not* crossing.

**Real vs. built:** fusion + F1–F6 scoring is real (`server/src/suspicion/scorer.py`). YAMNet audio cues are real and
already wired. The staged arrival timing is orchestrated.
**Effort:** medium — mostly UI (stepped meter animation + chip reveal). **Risk:** low.

---

## 3. Judge-in-the-loop — **strongest ethics beat**

**The beat.** When the verify queue comes up, don't click it. Hand it to a judge: *"You're the operator. Look at the
evidence panel. Flag, or dismiss?"* They decide, out loud, over Teams; Connie clicks what they say. Then the reveal:
*"Notice what just happened — the system waited. It could not have gone further without you. That's not a policy
we wrote down, it's the only path the code has."*

**Why it lands.** Turns the human-gate claim from a slide bullet into something the judge personally experienced.
It also gives them agency in the demo, which is disproportionately memorable.

**Real vs. built:** entirely real — the machine ceiling is enforced in `verify_entity`.
**Effort:** ~zero. **Risk:** low (don't hand over mouse control; just ask them to call it and click for them).

---

## 4. Show the false positive — **credibility beat**

**The beat.** Deliberately run a scenario that *should* trip a naive system and let ours catch itself: a delivery
driver, night-time, loitering, unfamiliar vehicle. Candidate raises → operator opens the verify panel → whitelist
check returns a match → dismissed, logged to the evidence chain. *"Every demo you'll see today shows you the hit.
This is the miss — and this is why the miss doesn't end with someone's door being kicked in."*

**Why it lands.** Nobody volunteers their failure mode. Doing it deliberately reads as confidence, and it pre-empts
the sharpest question a judge can ask.

**Real vs. built:** whitelist + dismiss + evidence logging are real.
**Effort:** low. **Risk:** low. **Pairs with:** the honesty ledger slide — this is that slide, demonstrated.

---

## 5. Kill the network live — **the uniquely-SA beat**

**The beat.** Mid-demo, unplug. Pull the server (or the tunnel) while the ops console is mid-stream. The dashboard
does **not** go blank — it greys, marks itself stale with a timestamp, and keeps the last-known state. The camera
agent keeps detecting and queues locally. Reconnect: `GET /v1/events/since` catches up and the queued sightings
flood in, in order. *"Stage 6 load shedding. Fibre down. Every other system on this call is a blank screen right now."*

**Why it lands.** It's the graceful-degradation principle made physical, and it's the single most South African
thing we can put on a screen. Also: it's *real code that already exists* — Sbu built the catch-up endpoint and the
stale-marking rule is UI law #4.

**Effort:** low-medium (mostly proving the UI stale state is real). **Risk:** medium — rehearse the reconnect
until it's boring, and have the "already reconnected" fallback frame ready.

---

## 6. Split-screen: today vs. BEACON

**The beat.** Two panels, one clock. Left: how this incident is handled today — nothing, nothing, nothing, then a
claim form arrives at 09:00 the next morning. Right: the same timeline with BEACON — sighting, sighting, fusion,
verify, dispatch, all before 00:30. Same scrubber drives both.

**Why it lands.** Legibility. A judge who has followed nothing technical still gets the value in four seconds.
**Effort:** medium (it's a bespoke view). **Risk:** low. **Note:** good candidate for the *slides* rather than the
live app, if build time is short.

---

## 7. The receipt (close on an artifact)

**The beat.** Last click of the demo: generate the incident report. The hash-chained trail — every action, every
actor, every timestamp, SHA-linked. Show the chain. *"This is what we'd hand an investigator. Not a screenshot of a
dashboard — a tamper-evident record of exactly who decided what, and when."*

**Why it lands.** Demos usually end on a red alert. Ending on a *document* says "we thought about the day after."
**Real vs. built:** `GET /v1/incidents/{id}/report` exists and returns the full evidence trail.
**Effort:** low (render it nicely). **Risk:** none.

---

## 8. Live suburb lookup (high risk / high reward)

**The beat.** In the cold open, don't drive a rehearsed path — ask a judge to name a Johannesburg suburb. Type it
live. The map flies there and shows *their* real claims history plus tonight's forecast for that hex.

**Why it lands.** Nothing proves "this is real data and not a screenshot" like an unrehearsed input.
**Risk: high** — only attempt if the claims data covers enough suburbs to never return an empty map, and rehearse
the graceful "we don't have coverage there yet, here's the nearest" path. **Have a scripted fallback suburb ready.**

---

## Recommended cut (if we could only keep four)

**3 (judge-in-the-loop)** + **2 (fusion orchestra)** + **5 (kill the network)** + **7 (the receipt)**.
Cheapest to build, hardest to copy, and together they tell one story: *evidence that agrees, a human who decides,
a system that survives, and a record that holds up.* The gun-and-plate detection then becomes the **vehicle** for
those beats rather than the point of them — which is also what makes it safe if Sali's weapon fine-tune doesn't land.

---

## What each concept still needs from whom

| Concept | Needs | From |
|---|---|---|
| 1 Time Machine | replay generator + timeline UI; real claim picked out of the dataset | Lethabo (UI) + Ndu (claim selection) |
| 2 Fusion Orchestra | stepped confidence meter + factor-chip reveal in ops console | Lethabo/Connie (UI) — logic already real |
| 3 Judge-in-the-loop | nothing — script line only | Demo script |
| 4 False positive | a whitelist entry seeded before the demo + scripted line | Sbu (seed) + script |
| 5 Kill the network | verify stale-state UI is real, rehearse reconnect | Lethabo (UI) — endpoint already real |
| 6 Split-screen | bespoke view or slide | Connie or slides |
| 7 The receipt | render `/v1/incidents/{id}/report` as a readable document | Lethabo (UI) — endpoint already real |
| 8 Suburb lookup | geocoded claims coverage | **Ndu — currently blocked, nothing landed** |

Note the pattern: six of eight concepts are **UI work over logic that already exists**. The backend is not the
bottleneck for any of them.
