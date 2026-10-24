"""Normalize any input into one stimulus brief. Images get a vision description when a real provider is available."""
from __future__ import annotations

import asyncio
import base64
import re

from ..llm import Meter, llm

VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "headline_text": {"type": "string"}, "other_text": {"type": "string"}, "visual_description": {"type": "string"},
        "visual_hierarchy": {"type": "string"}, "call_to_action": {"type": "string"}, "tone": {"type": "string"},
        "implied_audience": {"type": "string"}, "price_visible": {"type": "boolean"}, "proof_elements": {"type": "string"},
    },
    "required": ["headline_text", "other_text", "visual_description", "visual_hierarchy", "call_to_action", "tone", "implied_audience", "price_visible", "proof_elements"],
    "additionalProperties": False,
}

VISION_SYSTEM = "You describe marketing creatives precisely for a research panel that cannot see the image. Report what is literally there; do not evaluate. JSON only."

DOC_SCHEMA = {
    "type": "object",
    "properties": {
        "what_it_is": {"type": "string", "description": "One line: what kind of document this is (pitch deck, one-pager, price list...)"},
        "summary": {"type": "string", "description": "4-8 sentences: the product or idea, its main claims, offers and who it is for, as the document states them"},
        "numbers": {"type": "string", "description": "Prices, discounts, specs or other figures it states, or 'none'"},
    },
    "required": ["what_it_is", "summary", "numbers"],
    "additionalProperties": False,
}

DOC_SYSTEM = "You summarise documents for a research panel that cannot open them. Report what is literally there; do not evaluate or add anything. JSON only."
NOTE_CHARS = 6000  # text notes are passed on as written, up to this length


def _parse_data_url(url: str) -> tuple[str, str] | None:
    m = re.match(r"data:(image/\w+);base64,(.+)$", url, re.S)
    return (m.group(1), m.group(2)) if m else None


async def describe_image(data_url: str, meter: Meter, title: str) -> dict:
    parsed = _parse_data_url(data_url)
    fake = lambda: {"headline_text": title, "other_text": "", "visual_description": "Uploaded image (vision description unavailable without an API key).",
                    "visual_hierarchy": "", "call_to_action": "", "tone": "", "implied_audience": "", "price_visible": False, "proof_elements": ""}
    if not parsed:
        return fake()
    media, b64 = parsed
    try:
        base64.b64decode(b64[:64] + "===")
    except Exception:
        return fake()
    user = [
        {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
        {"type": "text", "text": f"Describe this creative titled '{title}'."},
    ]
    return await llm().json(role="analyst", system=VISION_SYSTEM, user=user, schema=VISION_SCHEMA, meter=meter, fake=fake, max_tokens=3000)


async def describe_pdf(data_url: str, meter: Meter, name: str) -> dict:
    fake = lambda: {"what_it_is": "PDF", "summary": "Attached PDF (documents are read only with an API key).", "numbers": "none"}
    m = re.match(r"data:application/pdf;base64,(.+)$", data_url, re.S)
    if not m:
        return fake()
    user = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": m.group(1)}},
        {"type": "text", "text": f"Summarise the attached document '{name}'."},
    ]
    return await llm().json(role="analyst", system=DOC_SYSTEM, user=user, schema=DOC_SCHEMA, meter=meter, fake=fake, max_tokens=3000)


def _clean(x: str) -> str:
    return (x or "").strip().rstrip(".")


def _blank(x: str) -> bool:
    return _clean(x).lower() in ("", "none", "n/a", "no")


async def describe_attachment(att: dict, meter: Meter) -> str:
    """One paragraph the crowd can read about an attached file: notes as written, images and PDFs described."""
    name, typ = att.get("name", "file"), att.get("type", "")
    try:
        if att.get("text"):
            return f"Attached note '{name}':\n{att['text'].strip()[:NOTE_CHARS]}"
        if typ.startswith("image/") and att.get("data"):
            v = await describe_image(att["data"], meter, name)
            words = " ".join(f"\"{_clean(t)}\"" for t in (v["headline_text"], v["other_text"]) if not _blank(t))
            return (f"Attached image '{name}' shows: {_clean(v['visual_description'])}. " + (f"Text on it: {words}. " if words else "It has no text. ")
                    + (f"Call to action: {_clean(v['call_to_action'])}. " if not _blank(v["call_to_action"]) else "")
                    + f"Tone: {_clean(v['tone'])}. Price visible: {'yes' if v['price_visible'] else 'no'}.")
        if typ == "application/pdf" and att.get("data"):
            d = await describe_pdf(att["data"], meter, name)
            return f"Attached document '{name}' ({_clean(d['what_it_is'])}): {_clean(d['summary'])}. Figures it states: {_clean(d['numbers'])}."
    except Exception as e:  # one unreadable file shouldn't stop the run
        if type(e).__name__ == "BudgetExceeded":
            raise
        return f"Attached file '{name}' could not be read."
    return f"Attached file '{name}' ({typ or 'unknown type'}) is not a format the panel can read."


async def build_brief(stimulus: dict, meter: Meter) -> dict:
    """Returns the stimulus with `brief` finalized: offer, URL, image and attached files folded into the text agents read."""
    s = dict(stimulus)
    parts = [s.get("brief", "").strip()]
    if s.get("type") == "offer" and s.get("offer"):
        o = s["offer"]
        parts.insert(0, f"Offer: {o.get('product')}. Price {o.get('price')}. {o.get('discount')}. {o.get('urgency')}. Terms: {o.get('terms')}.")
    if s.get("type") == "website" and s.get("url"):
        parts.insert(0, f"Website: {s['url']}.")
    if s.get("imageUrl"):
        v = await describe_image(s["imageUrl"], meter, s.get("title", "creative"))
        s["vision"] = v
        parts.insert(0, (f"The creative shows: {v['visual_description']} Headline text: \"{v['headline_text']}\". Other text: {v['other_text']}. "
                         f"Visual hierarchy: {v['visual_hierarchy']}. CTA: {v['call_to_action'] or 'none visible'}. Tone: {v['tone']}. "
                         f"Price visible: {'yes' if v['price_visible'] else 'no'}. Proof elements: {v['proof_elements'] or 'none'}."))
    attachments = s.get("attachments") or []
    if attachments:
        parts += await asyncio.gather(*(describe_attachment(a, meter) for a in attachments))
        # The file contents are in the brief now; keep only what the UI lists.
        s["attachments"] = [{"name": a.get("name"), "type": a.get("type"), "size": a.get("size", 0)} for a in attachments]
    s["brief"] = "\n\n".join(p for p in parts if p)
    return s


def stimulus_block(s: dict) -> str:
    """Shared, cacheable text every agent reads."""
    kind = {"creative": "an advertising creative / poster", "website": "a website / landing page", "offer": "a commercial offer", "idea": "a business idea"}[s["type"]]
    return (f"STIMULUS ({kind}): \"{s.get('title', 'Untitled')}\"\n{s['brief']}\n"
            f"Intended audience according to the maker: {s.get('targetAudience') or 'not stated'}.")
