"""Normalize any input into one stimulus brief. Images get a vision description when a real provider is available."""
from __future__ import annotations

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
    return await llm().json(role="analyst", system=VISION_SYSTEM, user=user, schema=VISION_SCHEMA, meter=meter, fake=fake, max_tokens=900)


async def build_brief(stimulus: dict, meter: Meter) -> dict:
    """Returns the stimulus with `brief` finalized and `vision` attached when an image was provided."""
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
    s["brief"] = "\n".join(p for p in parts if p)
    return s


def stimulus_block(s: dict) -> str:
    """Shared, cacheable text every agent reads."""
    kind = {"creative": "an advertising creative / poster", "website": "a website / landing page", "offer": "a commercial offer", "idea": "a business idea"}[s["type"]]
    return (f"STIMULUS ({kind}): \"{s.get('title', 'Untitled')}\"\n{s['brief']}\n"
            f"Intended audience according to the maker: {s.get('targetAudience') or 'not stated'}.")
