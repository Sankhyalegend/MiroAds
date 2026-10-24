# Crowd Validator

Upload a creative, website, offer or business idea. A market scan first looks up what is already out there
(competitors, prices, recent news). A crowd sampled from a library of thousands of simulated people (different jobs,
countries, incomes, ideologies, personalities, moods) reacts individually, each knowing only the part of the market
someone like them would have come across. They argue in a social app (posts, replies, reposts, likes), everyone is
interviewed at the end about what they concluded, and a research team writes it up: score, stated intent, NPS,
segment breakdown, clustered objections and takeaways, market position, missing KPIs, better variants, methodology and
limitations. The run streams live into an animated network of agents, or a readable feed of the app they use.

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
uv run python -m uvicorn app.main:app --port 8000   # via python: Windows Application Control can block the uvicorn.exe launcher
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
| 0b Market scan | Web search (8 searches) for competitors, prices, news; a second call extracts them as JSON. Each agent gets the slice someone like them would know (by tech adoption and information diet; ~30% of buyers/users already own an alternative), and news can make them wary or excited | market (crowd model by default), analyst |
| 1 First impressions | Every agent scores alone: score, intent, objection, missing, reasoning | crowd |
| 2 Social app | Each round a slice of the crowd reads a ranked feed and posts / replies / reposts / likes / does nothing; everyone opens the app at least once; score changes must cite a post | crowd |
| 2b Exit interviews | Everyone says what they concluded: intent, takeaway, mind change, vs alternatives, recommend 0-10, the one fix | crowd |
| 3 Research team | 10 expert lenses (incl. a competitive analyst) audit the numbers: missing KPIs, risks, caveats | analyst |
| 4 Report | Stats computed in code (intent from what agents said, NPS, themes); the model writes verdict, market position, variants, limitations | analyst |

Turn the market scan off per run on the Upload page. Without an API key the fake provider returns a labelled simulated
market; if web search fails the run continues without one and says why.

Events (`stage, market, impression, post, reply, repost, like, exposure, mind_change, round, interview, expert, done`)
are persisted with a sequence number and streamed over `WS /runs/{id}/events?from_seq=N`, so a page refresh replays the run.

## Cost (list price, Haiku 5.5 crowd)

| Run (market scan on) | Dev mode (analysts on Haiku) | Full (analysts on Sonnet 5.5) |
|---|---|---|
| 100 agents, 3 rounds | $0.23 (measured) | ~$1.15 |
| 300 agents, 5 rounds | ~$0.40 | ~$1.35 |
| 1,000 agents, 5 rounds | ~$0.95 | ~$1.95 |

The market scan is about $0.10 of that ($10 per 1,000 web searches plus ~120K input tokens on Haiku); turning it off
saves that. A 1,000-agent run in full mode is close to the default $2 budget.

Guardrails: per-run budget (`RUN_BUDGET_USD`), early stop on budget, and set a spend cap on the API key itself.
