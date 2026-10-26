# Deploying Crowd Validator

The app runs as one container: the website and its API on a single port. You need three things on the host:

1. **Your Anthropic API key**, set as `ANTHROPIC_API_KEY`. Never put it in a file you upload or commit.
2. **A password**, set as `APP_PASSWORD`. Without one, anyone who finds the address can start paid tests on your key.
   The browser asks for it once (type any user name).
3. **A persistent disk mounted at `/data`**, where the database lives (the 40,000-person village, your tests and reports).
   Without it, everything is lost when the container restarts.

## The two files

- `crowd-validator-source.zip`: the code, the `Dockerfile` and this guide. No keys, no data.
- `crowd-validator-data.zip`: `crowd.db`, the database with the 40,000-person village and your past tests. Building
  the village again costs about $6, so ship this one.

Before building, unzip the source, then put the database at `backend/seed/crowd.db`:

```bash
unzip crowd-validator-source.zip -d crowd-validator
cd crowd-validator
mkdir -p backend/seed
unzip ../crowd-validator-data.zip -d backend/seed
```

The first time the container starts, it copies `backend/seed/crowd.db` to `/data/crowd.db`. After that it uses
`/data`, so later builds never overwrite your tests.

## Option A: your own server with Docker (a VPS, any provider)

```bash
docker build -t crowd-validator .
docker run -d --name crowd-validator --restart unless-stopped -p 8000:8000 \
  -e ANTHROPIC_API_KEY=your-key -e APP_PASSWORD=choose-a-password \
  -v crowd-data:/data crowd-validator
```

Open `http://your-server:8000`. For a public address, put HTTPS in front (for example Caddy:
`caddy reverse-proxy --from your-domain.com --to localhost:8000`); without HTTPS the password travels unencrypted.

## Option B: a hosting service that builds a Dockerfile (Railway, Fly.io, Render)

Create a service from this folder's `Dockerfile` and set:

| Setting | Value |
|---|---|
| Variables | `ANTHROPIC_API_KEY`, `APP_PASSWORD` (optional: `RUN_BUDGET_USD`, default 2) |
| Volume / disk | mounted at `/data`, 1 GB is plenty |
| Port | 8000 (the app also reads `PORT` if the host sets it) |
| Health check | `/api/health` (it answers without the password) |

These services give you HTTPS automatically. Railway (`railway up`) and Fly.io (`fly deploy`) upload the folder from
your computer, seed database included. Render builds from a Git repository; the database is too big for GitHub
(over 100 MB), so there you would upload it to the disk yourself or build the village on the server instead.

## Running it

- Every test is confirmed with its estimated cost first, and stops at `RUN_BUDGET_USD` per test (default $2). Keep
  a spending cap on the API key too.
- `DEV_MODE=true` (the default) writes the research team's notes with the cheaper model; set `DEV_MODE=false` for
  Sonnet, which costs several times more per test.
- To update the app, build and start the container again; the data in `/data` stays.
- To build a fresh village on the server instead of shipping the database (about $6):
  `docker exec crowd-validator .venv/bin/python scripts/build_library_batch.py --n 40000 --seed 100001 --dedupe-names`
