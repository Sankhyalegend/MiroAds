"""Runtime settings. Everything comes from environment variables / backend/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


# USD per million tokens. Source: platform.claude.com/docs/en/about-claude/pricing (2026-10-18).
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.10, "cache_write": 2.50},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "fake": {"in": 0.0, "out": 0.0, "cache_read": 0.0, "cache_write": 0.0},
}
# Claude's web search tool, billed per search on top of tokens ($10 per 1,000).
WEB_SEARCH_USD = 0.01


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY", ""))
    # "auto" -> anthropic when a key is present, otherwise the deterministic fake provider.
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))
    crowd_model: str = field(default_factory=lambda: _env("CROWD_MODEL", "claude-haiku-5-5"))
    analyst_model: str = field(default_factory=lambda: _env("ANALYST_MODEL", "claude-sonnet-5-5"))
    # Market scan research. Search results are read in full (100K+ input tokens), so it defaults to the crowd model.
    market_model: str = field(default_factory=lambda: _env("MARKET_MODEL", _env("CROWD_MODEL", "claude-haiku-5-5")))
    # Dev mode runs the analyst roles (experts, judge) on the crowd model to save money.
    dev_mode: bool = field(default_factory=lambda: _env("DEV_MODE", "true").lower() in ("1", "true", "yes"))
    run_budget_usd: float = field(default_factory=lambda: float(_env("RUN_BUDGET_USD", "2.0")))
    # "off" disables extended thinking for crowd calls (cheaper, no truncation); "adaptive" leaves the model default.
    crowd_thinking: str = field(default_factory=lambda: _env("CROWD_THINKING", "off"))
    max_concurrency: int = field(default_factory=lambda: int(_env("MAX_CONCURRENCY", "24")))
    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", str(ROOT / "data" / "crowd.db"))))
    cors_origins: list[str] = field(default_factory=lambda: _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","))

    @property
    def effective_provider(self) -> str:
        if self.provider == "auto":
            return "anthropic" if self.api_key else "fake"
        return self.provider

    def model_for(self, role: str) -> str:
        if self.effective_provider == "fake":
            return "fake"
        if role == "crowd":
            return self.crowd_model
        if role == "market":
            return self.market_model
        return self.crowd_model if self.dev_mode else self.analyst_model


settings = Settings()
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
