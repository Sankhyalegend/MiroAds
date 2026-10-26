# Crowd Validator as one container: the website and its API on one port. See DEPLOY.md.

# 1. Build the website.
FROM node:24-slim AS site
WORKDIR /site
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The site talks to the API on the same server, under /api.
ENV VITE_API_URL=/api
RUN npm run build

# 2. The API, which also serves the website.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=site /site/dist /app/frontend/dist
ENV DB_PATH=/data/crowd.db STATIC_DIR=/app/frontend/dist PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
# On the first start, the village in backend/seed/crowd.db (if you put it there before building) is copied to the data
# folder, which should be a persistent disk so tests and reports survive restarts.
CMD ["sh", "-c", "mkdir -p \"$(dirname \"$DB_PATH\")\" && { [ -f \"$DB_PATH\" ] || [ ! -f seed/crowd.db ] || cp seed/crowd.db \"$DB_PATH\"; } && exec .venv/bin/python -m uvicorn app.main:web --host 0.0.0.0 --port \"$PORT\""]
