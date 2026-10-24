"""LLM gateway: one place for model routing, structured outputs, prompt caching, concurrency,
retries, cost metering, budgets, and the deterministic fake provider used when no key is set."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .config import PRICING, WEB_SEARCH_USD, settings

log = logging.getLogger("llm")


class BudgetExceeded(RuntimeError):
    pass


# Keywords Anthropic structured outputs reject (as of 2026-10). Constraints are enforced in code instead,
# and moved into the description so the model still sees the intent.
_UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "minLength", "maxLength", "pattern", "multipleOf", "format"}


def sanitize_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [sanitize_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    hints = []
    for k, v in schema.items():
        if k in _UNSUPPORTED:
            hints.append(f"{k} {v}")
            continue
        out[k] = sanitize_schema(v)
    if hints:
        desc = out.get("description", "")
        out["description"] = (desc + (" " if desc else "") + "(" + ", ".join(hints) + ")").strip()
    return out


class LLMRefusal(RuntimeError):
    pass


@dataclass
class Meter:
    """Per-run accounting. Shared by every call made on behalf of a run."""
    budget_usd: float
    cost_usd: float = 0.0
    calls: int = 0
    searches: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0})
    on_update: Optional[Callable[["Meter"], None]] = None

    def add(self, model: str, usage: Any) -> None:
        p = PRICING.get(model, PRICING["fake"])
        i = getattr(usage, "input_tokens", 0) or 0
        o = getattr(usage, "output_tokens", 0) or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        ws = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
        self.tokens["in"] += i; self.tokens["out"] += o; self.tokens["cache_read"] += cr; self.tokens["cache_write"] += cw
        self.cost_usd += (i * p["in"] + o * p["out"] + cr * p["cache_read"] + cw * p["cache_write"]) / 1_000_000
        if model != "fake":
            self.cost_usd += ws * WEB_SEARCH_USD
        self.searches += ws
        self.calls += 1
        if self.on_update:
            self.on_update(self)

    def check(self) -> None:
        if self.cost_usd > self.budget_usd:
            raise BudgetExceeded(f"run budget ${self.budget_usd:.2f} exceeded (${self.cost_usd:.2f})")


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class LLM:
    def __init__(self) -> None:
        self.provider = settings.effective_provider
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self._client = None
        if self.provider == "anthropic":
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=settings.api_key, max_retries=3)
        log.info("LLM provider=%s crowd=%s analyst=%s dev_mode=%s", self.provider, settings.model_for("crowd"), settings.model_for("analyst"), settings.dev_mode)

    async def _create(self, stream: bool = False, **kwargs: Any) -> Any:
        """messages.create under the concurrency cap (streamed when the output can be long). The SDK already retried
        transient errors 3x; this also rides out rate-limit bursts."""
        assert self._client is not None
        async with self._sem:
            for attempt in range(4):
                try:
                    if stream:
                        async with self._client.messages.stream(**kwargs) as s:
                            return await s.get_final_message()
                    return await self._client.messages.create(**kwargs)
                except Exception as e:
                    if attempt < 3 and type(e).__name__ in ("RateLimitError", "APIConnectionError", "InternalServerError", "OverloadedError", "APITimeoutError"):
                        await asyncio.sleep(1.5 * (2 ** attempt) + random.random())
                        continue
                    raise
        raise RuntimeError("unreachable")

    async def research(self, *, role: str, system: str, user: str, meter: Meter, fake: Callable[[], dict], max_searches: int = 8, max_tokens: int = 32000) -> dict:
        """Free-text research with Claude's web search tool. Returns {"text", "sources": [{"url", "title"}], "searches", "stop"}.
        Web search always attaches citations, which structured outputs reject, so callers extract JSON in a second call.
        Uses the basic tool: in testing, dynamic filtering (web_search_20260209+) on Haiku batched searches past
        max_uses and came back empty, while the basic tool returned sourced prices."""
        meter.check()
        model = settings.model_for(role)
        if self.provider == "fake":
            await asyncio.sleep(0.3)
            out = fake()
            meter.add("fake", FakeUsage(output_tokens=len(out["text"]) // 4))
            return out

        messages: list[dict] = [{"role": "user", "content": user}]
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
        base: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=[{"type": "text", "text": system}], tools=tools, output_config={"effort": "medium"})
        resp = await self._create(stream=True, **base, messages=messages)
        texts: list[str] = []
        sources: dict[str, str] = {}
        searches = 0
        turn_so_far: list[Any] = []  # the assistant turn across pauses, sent back to resume it
        for turn in range(4):
            meter.add(model, resp.usage)
            turn_so_far += resp.content
            searches += getattr(getattr(resp.usage, "server_tool_use", None), "web_search_requests", 0) or 0
            for b in resp.content:
                if b.type == "text":
                    texts.append(b.text)
                    for c in getattr(b, "citations", None) or []:
                        if getattr(c, "url", None):
                            sources.setdefault(c.url, getattr(c, "title", "") or c.url)
                elif b.type == "web_search_tool_result" and isinstance(b.content, list):
                    for r in b.content:
                        if getattr(r, "url", None):
                            sources.setdefault(r.url, getattr(r, "title", "") or r.url)
            if resp.stop_reason != "pause_turn" or turn == 3:
                break
            # A long search turn can pause; sending the paused turn back unchanged resumes it.
            resp = await self._create(stream=True, **base, messages=messages + [{"role": "assistant", "content": turn_so_far}])
        log.info("research: model=%s turns=%d stop=%s searches=%d text=%d chars sources=%d", model, turn + 1, resp.stop_reason, searches, sum(map(len, texts)), len(sources))
        if resp.stop_reason == "refusal":
            raise LLMRefusal("research refused")
        return {"text": "".join(texts).strip(), "sources": [{"url": u, "title": t} for u, t in sources.items()], "searches": searches, "stop": resp.stop_reason}

    async def json(
        self,
        *,
        role: str,
        system: str,
        user: str | list[dict],
        schema: dict,
        meter: Meter,
        fake: Callable[[], dict],
        max_tokens: int = 900,
        effort: str | None = None,
        temperature_hint: float | None = None,  # ignored by Claude 5.x; kept for provider parity
    ) -> dict:
        """Structured JSON call. `system` is cached (shared across the run). `fake` supplies the answer offline."""
        meter.check()
        model = settings.model_for(role)
        if self.provider == "fake":
            # Simulate latency so the UI animates like the real thing, and tokens so metering code paths run.
            await asyncio.sleep(0.012 + random.random() * 0.03)
            out = fake()
            meter.add("fake", FakeUsage(input_tokens=len(system) // 4 + len(str(user)) // 4, output_tokens=len(json.dumps(out)) // 4))
            return out

        assert self._client is not None
        content = user if isinstance(user, list) else [{"type": "text", "text": user}]
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": sanitize_schema(schema)}, "effort": effort or ("low" if role == "crowd" else "medium")},
        )
        # Crowd role-play doesn't benefit from extended thinking, and thinking tokens count against max_tokens
        # (they truncated persona JSON and tripled cost). Haiku 5.5 accepts disabling it at effort <= high.
        if role == "crowd" and settings.crowd_thinking == "off" and model.startswith("claude-haiku"):
            kwargs["thinking"] = {"type": "disabled"}
        resp = await self._create(**kwargs)
        meter.add(model, resp.usage)
        if resp.stop_reason == "refusal":
            raise LLMRefusal(getattr(getattr(resp, "stop_details", None), "explanation", "refused"))
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Structured outputs guarantee valid JSON unless truncated by max_tokens.
            if resp.stop_reason == "max_tokens":
                raise RuntimeError("LLM JSON truncated at max_tokens; raise max_tokens for this call")
            raise

    async def text(self, *, role: str, system: str, user: str | list[dict], meter: Meter, fake: Callable[[], str], max_tokens: int = 1200) -> str:
        meter.check()
        model = settings.model_for(role)
        if self.provider == "fake":
            await asyncio.sleep(0.02)
            out = fake()
            meter.add("fake", FakeUsage(output_tokens=len(out) // 4))
            return out
        assert self._client is not None
        content = user if isinstance(user, list) else [{"type": "text", "text": user}]
        async with self._sem:
            resp = await self._client.messages.create(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_config={"effort": "low" if role == "crowd" else "medium"},
            )
        meter.add(model, resp.usage)
        if resp.stop_reason == "refusal":
            raise LLMRefusal("refused")
        return next((b.text for b in resp.content if b.type == "text"), "")


_llm: LLM | None = None


def llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm


def now_ms() -> float:
    return time.time() * 1000
