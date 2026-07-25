# dashboard/app

The real BEACON ops dashboard — Vite + React + TypeScript + Tailwind v4.
This is the porting destination described in `design/PROMPT-PACK.md` §3.

## Run it

```
npm install
npm run dev
```

Dev server proxies `/health`, `/v1/*`, `/ws/*` to `http://localhost:8000`
(the real FastAPI server — `server/src/main.py`). Start that first.

## Structure

- `src/theme/tokens.ts` — the design tokens, TS-typed. Verbatim mirror of
  `src/index.css`'s `:root` block, which itself is verbatim from
  `design/PROMPT-PACK.md` §1. **This is the single source of truth for color.**
  Any ported screen with a hardcoded hex value gets that value replaced with
  a reference to `colors.*` from this file — that's the first porting step,
  every time.
- `src/api/client.ts` — REST client (`getHealth`, `getRisk`, `getHotspots`).
  Response shapes are copied from the real Pydantic models in
  `server/src/api/*.py`; if those change, update this file in the same PR.
- `src/api/ws.ts` — `/ws/ops` client (`OpsSocket`). Event names match what
  the server actually emits today (grep `server/src` for `"event":` to
  re-verify) — `route.updated` / `forecast.updated` are documented in the
  server's docstring but not wired up yet, so treat them as "coming soon."
- `src/screens/` — one file per ported PROMPT-PACK screen (2.1–2.12). Empty
  until a Claude Design code export lands.
- `src/components/` — shared pieces used across screens. Empty until the
  first screen needs to share something.

## Porting a screen from Claude Design

1. Drop the raw, unmodified code export at `design/exports/<screen-name>/`
   (per `design/PROMPT-PACK.md` §3 — never edit the export in place).
2. Create `src/screens/<ScreenName>.tsx`, port the JSX/logic in.
3. Replace every hardcoded hex/color with the matching `colors.*` token.
4. Replace any mock data with a real call through `src/api/client.ts` or
   `src/api/ws.ts` — if the screen needs an endpoint that doesn't exist yet,
   say so instead of quietly leaving the mock in.
5. Open a PR per `design/README.md`.
