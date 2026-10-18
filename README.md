# Crowd Validator

Upload a creative, website, offer or business idea. A crowd sampled from a library of thousands of simulated people
(different jobs, countries, incomes, ideologies, personalities, moods) reacts individually, argues on a social feed,
and a research team writes it up: score, segment breakdown, clustered objections, missing KPIs, better variants,
methodology and limitations. The whole run streams live into an animated network of agents and the lines between them.

## Layout

- `frontend/` Vite + React + TypeScript. WebGL network (PixiJS), zustand store, mock engine for offline demos.
- `backend/` FastAPI + SQLite. LLM gateway (Anthropic SDK, structured outputs, prompt caching, metering, budgets,
  deterministic fake provider), persona frame + generator + sampler, 4-stage engine, WebSocket event stream.

## Run it

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
copy .env.example .env        # add ANTHROPIC_API_KEY, or leave empty to use the $0 fake provider
uv sync
uv run python scripts/build_library.py --n 2000     # one-time persona library (10,000 is about $3 on Haiku 5.5)
uv run uvicorn app.main:app --port 8000
```

Frontend (Node 18+):

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Smoke test the API end to end: `powershell -File backend/scripts/smoke_run.ps1 -Crowd 150 -Rounds 3`

## Pipeline

| Stage | What happens | Model |
|---|---|---|
| 0 Brief | Normalize input; images get a vision description | analyst |
| 1 First impressions | Every agent scores alone: score, intent, objection, missing, reasoning | crowd |
| 2 Social rounds | Active agents read a ranked feed and post / reply / repost / do nothing; scores drift | crowd |
| 3 Research team | 9 expert lenses audit the numbers: missing KPIs, risks, caveats | analyst |
| 4 Report | Stats computed in code; the model writes verdict, notes, variants, limitations | analyst |

Events (`stage, impression, post, reply, repost, exposure, mind_change, round, expert, done`) are persisted with a
sequence number and streamed over `WS /runs/{id}/events?from_seq=N`, so a page refresh replays the run.

## Cost (list price, Haiku 5.5 crowd)

| Run | Dev mode (analysts on Haiku) | Full (analysts on Sonnet 5.5) |
|---|---|---|
| 100 agents, 3 rounds | ~$0.05 | ~$0.90 |
| 300 agents, 5 rounds | ~$0.15 | ~$1.00 |
| 1,000 agents, 5 rounds | ~$0.45 | ~$1.30 |

Guardrails: per-run budget (`RUN_BUDGET_USD`), early stop on budget, and set a spend cap on the API key itself.
