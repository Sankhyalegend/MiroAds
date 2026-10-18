"""Per-stimulus-type knowledge: scoring dimensions, expert KPI prompts, and the fake provider's
objection/praise vocabulary. The LLM path uses only `DIMENSIONS` and `KPI_HINTS`; the rest feeds the fake."""
from __future__ import annotations

DIMENSIONS: dict[str, list[tuple[str, float]]] = {
    "creative": [("Clarity", 0.25), ("Desirability", 0.25), ("Credibility", 0.15), ("Differentiation", 0.15), ("Shareability", 0.10), ("Price-value fit", 0.10)],
    "website": [("Clarity", 0.20), ("Credibility", 0.25), ("Desirability", 0.20), ("Price-value fit", 0.15), ("Usability", 0.20)],
    "offer": [("Price-value fit", 0.30), ("Credibility", 0.25), ("Clarity", 0.15), ("Urgency fit", 0.15), ("Desirability", 0.15)],
    "idea": [("Problem clarity", 0.15), ("Desirability", 0.20), ("Viability", 0.25), ("Feasibility", 0.15), ("Differentiation", 0.15), ("Risk", 0.10)],
}

KPI_HINTS: dict[str, str] = {
    "creative": "CTR by segment, 5-second comprehension, unaided brand recall, cost per qualified click, creative fatigue rate",
    "website": "scroll depth to pricing, hero-to-signup conversion, trust-signal exposure, mobile bounce, time to first value",
    "offer": "conversion by income band, refund/chargeback rate, discount elasticity, urgency lift vs control, post-promo retention",
    "idea": "CAC payback, activation rate, net revenue retention, gross margin at scale, time-to-value, wedge-customer concentration",
}

OBJECTIONS: dict[str, list[str]] = {
    "creative": ["The headline doesn't say what the product does", "Price is nowhere on the creative, feels like it's hiding something", "Looks like every other premium gadget ad",
                 "The tagline is clever but I had to read it twice", "Can't tell who this is for", "Too dark, the product is barely visible", "No proof: no review, no number, no comparison", "The CTA is weak"],
    "website": ["I scrolled twice and still don't know the price", "Hero copy is all adjectives, no specifics", "No reviews or logos, so why would I trust it", "The signup form asks for too much up front",
                "The mobile menu is a mess", "Loads slow and the first thing I see is a cookie wall", "Pricing page compares to nothing", "Where is the 'how it works'?"],
    "offer": ["The discount is big enough to make me think the full price is fake", "'Ends Sunday' every week, I've seen this trick", "Terms say auto-renew, that's the real price",
              "A percentage off means nothing without the base price", "It's a bundle of things I don't need", "Why first 500 only? Feels manufactured", "I don't trust the brand yet", "No money-back guarantee"],
    "idea": ["Who pays, and how much? The model is hand-wavy", "Big players can copy this in a quarter", "The problem is real but small", "Acquisition cost will eat the margin",
             "Regulation is the actual moat and you don't mention it", "This is a feature, not a company", "The target user doesn't buy software, their boss does", "Why hasn't anyone done it? Usually there's a reason"],
}
MISSING: dict[str, list[str]] = {
    "creative": ["a price", "a concrete benefit in numbers", "social proof", "a clear CTA", "the product name in large type", "a comparison to what I use today"],
    "website": ["pricing above the fold", "customer logos or reviews", "a product screenshot", "a comparison table", "a free trial", "a security note"],
    "offer": ["the base price", "a guarantee", "what happens after the promo", "a single-item option", "a real deadline", "what 'limited' means"],
    "idea": ["a pricing model", "unit economics", "a wedge customer", "a go-to-market channel", "a defensibility story", "evidence the problem is painful"],
}
PRAISE: dict[str, list[str]] = {
    "creative": ["The mood is beautiful", "Tagline is memorable", "Clean, premium feel", "I get the vibe instantly", "Nice restraint, not shouty"],
    "website": ["Fast and clean", "The demo sold it", "Pricing is honest", "Good FAQ", "Real screenshots, finally"],
    "offer": ["Good value, I'd try it", "Clear and simple", "The bundle makes sense", "Early-bird feels fair", "Love a transparent price"],
    "idea": ["Clear problem, I've felt it", "The wedge is smart", "Timing looks right", "Explains itself in a sentence", "I'd pay for this"],
}

# The "research team" that audits every run. Each has a lens; the LLM writes the findings.
RESEARCH_TEAM: list[dict] = [
    {"name": "Lead researcher", "lens": "Overall validity of the signal: does the crowd's reaction answer the question asked, and what is it not telling us?"},
    {"name": "Quantitative analyst", "lens": "Statistics: sample size per segment, polarization, whether differences between segments are large enough to act on."},
    {"name": "CFO", "lens": "Unit economics, pricing power, margin, payback. Which numbers are missing to judge viability?"},
    {"name": "Growth marketer", "lens": "Acquisition: channel fit, message clarity, CTR/conversion KPIs, creative fatigue, what to A/B test first."},
    {"name": "UX researcher", "lens": "Comprehension, friction, trust cues, accessibility; what the first five seconds communicate."},
    {"name": "Behavioural scientist", "lens": "Biases at play: anchoring, scarcity, social proof, loss aversion; which cues help and which backfire."},
    {"name": "Product counsel", "lens": "Claims that need substantiation, regulatory exposure, terms and disclosure risks."},
    {"name": "Operations lead", "lens": "Deliverability: fulfilment, support load, returns, scaling constraints implied by the promise."},
    {"name": "Sceptic-in-residence", "lens": "The strongest case against. Assume the crowd is too kind; find what would make this fail."},
]
