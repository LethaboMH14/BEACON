# Contributing to BEACON

Five people, three days, one repo. This is the loop that keeps us fast without stepping on each other.

## The loop (everything follows it — code, docs, mockups, slides)

1. **Branch:** `git checkout -b <yourname>/<thing>` (e.g. `connie/ops-console-mock`, `ndu/geocode-cache`). Never commit straight to `main`.
2. **Build small:** one idea per PR, < 400 lines diff preferred. Behaviour change ⇒ update the matching `docs/` file + BUILD-LOG entry in the same PR.
3. **Open a PR:** the template auto-fills. Screenshots mandatory for anything visual (mockups, dashboard, charts).
4. **Review + amend:** the area owner (CODEOWNERS auto-requests them) reviews within a couple of hours; anyone else may comment. Amend by pushing new commits to the same branch — the PR updates live. Disagreements about design → propose an ADR in `docs/adr.md`, don't argue in code.
5. **Merge:** squash-merge once approved + CI green. Delete the branch.

## Seeing each other's adds

- On the repo page: **Watch → All activity** (everyone, day one). You'll get every PR, comment, and merge.
- The **Pull requests tab is the team's feed** — check it when you start and end a work block.
- Mockups and design additions land in `design/` via PRs like everything else, so they show up in the same feed with inline image previews you can comment on pixel-by-pixel.

## Where things go

| You're adding | Put it in | PR reviewer |
|---|---|---|
| UI mockups, exports, screen specs | `design/` (see its README) | Lethabo + one more |
| Vision models/notebooks | `vision/`, weights registered in `models.json` | Lethabo |
| Server endpoints | `server/` + contract update in docs/01 §5 (needs ADR if frozen) | Sbu owns, Lethabo reviews |
| Data pipelines, notebooks, model evals | `data/` | Sbu or Lethabo |
| Dashboard code | `dashboard/` | Connie owns, Lethabo reviews |
| Slides, business numbers | `docs/05` + `design/slides/` | Sali + Ndu cross-review |
| Decisions | `docs/adr.md` (append-only) | whole team |

## Hard rules (same as VUKA)

- Repo is **PUBLIC**: no secrets, no API keys, no `.env`, no tunnel URLs, no personal data (real faces/plates of strangers) — ever, in any commit.
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- `sim_` prefix on all simulated components, in code and filenames.
- Honesty ledger (docs/05 §6) applies to code comments and UI copy, not just slides.
