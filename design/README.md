# design/ — mockups and screen specs

All visual work lands here **via pull request** — that's how the team sees, comments on, and amends every addition (GitHub renders PNG diffs inline; reviewers can comment on the image in the PR).

## Structure

```
design/
├── ops-console/        # Connie: security ops screens
├── member-view/        # Connie: member/guardian screens
├── exec-view/          # Discovery analytics tab
├── slides/             # Sali + Ndu: pitch deck exports (PDF/PNG per version)
└── tokens/             # colours, type, spacing (from the VUKA Discovery theme handoff)
```

## Rules

1. **Filenames:** `YYYY-MM-DD_screen-name_v2.png` — date-prefixed so versions sort themselves.
2. **Figma:** paste the share link in the PR description AND export a PNG here — the repo must stand alone if Figma is unreachable during the pitch.
3. Every mockup PR states which docs/04 screen it implements and flags any deviation from the UI laws (docs/04 §4) — deviations need a reason, not silence.
4. No real personal data in mockups: team faces (consented) or generated placeholders only; fake plates only.
