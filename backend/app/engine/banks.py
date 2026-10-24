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
    {"name": "Competitive analyst", "lens": "Position against what is already on the market (from the market scan): price position, real differentiation, switching cost from what people already own, and which competitor wins each segment."},
]

# Offline stand-in for the market scan: a clearly labelled, generic market so the feature still demos without a key.
_PRODUCT_MARKET = {
    "category": "Consumer gadgets in this category (simulated)",
    "summary": "Simulated market: a well-known leader, a cheap marketplace option, a premium design rival and a DIY workaround already cover most of the need. Not real market data.",
    "price_range": "$12 DIY, $25-99 mainstream, $200+ premium",
    "competitors": [
        {"name": "Category leader", "maker": "Big brand", "price": "$99", "pitch": "The one most people have heard of", "liked_for": "reliable, lots of reviews", "complaints": "pricey, the app wants an account", "url": ""},
        {"name": "Budget pick", "maker": "Marketplace brand", "price": "$25", "pitch": "Does the basics for a quarter of the price", "liked_for": "cheap and good enough", "complaints": "flimsy, uneven quality", "url": ""},
        {"name": "Premium rival", "maker": "Design brand", "price": "$220", "pitch": "Beautiful object, premium materials", "liked_for": "looks great on a desk", "complaints": "overpriced for what it does", "url": ""},
        {"name": "Timer plug hack", "maker": "Generic", "price": "$12", "pitch": "A smart plug on a schedule does the main trick", "liked_for": "costs almost nothing", "complaints": "fiddly setup, no colour control", "url": ""},
    ],
    "news": [
        {"headline": "Shoppers trade down as gadget prices rise", "source": "Simulated Daily", "date": "2026", "gist": "Mid-priced devices lose share to cheap marketplace brands.", "url": "", "tone": "negative"},
        {"headline": "Reviewers warm to a new wave of well-designed home devices", "source": "Simulated Tech", "date": "2026", "gist": "Design-led products get strong reviews and social buzz.", "url": "", "tone": "positive"},
        {"headline": "Regulators look at subscription traps in connected devices", "source": "Simulated Times", "date": "2026", "gist": "Apps that lock features behind subscriptions draw complaints.", "url": "", "tone": "negative"},
    ],
    "buyer_complaints": ["apps that need an account", "short lifespan", "prices that hide subscriptions"],
    "substitutes": ["a smart plug on a timer", "doing nothing and living with it"],
}
_IDEA_MARKET = {
    "category": "Software and services for this need (simulated)",
    "summary": "Simulated market: an incumbent platform, agencies, a DIY spreadsheet-and-survey routine and a funded startup already compete for the same budget. Not real market data.",
    "price_range": "$0 DIY, $50-300/month tools, $5k+ agency projects",
    "competitors": [
        {"name": "Incumbent platform", "maker": "Large vendor", "price": "$300/month", "pitch": "The default enterprise choice", "liked_for": "trusted, integrates with everything", "complaints": "expensive, slow to set up", "url": ""},
        {"name": "Agency or consultants", "maker": "Various", "price": "$5,000+ per project", "pitch": "Humans do it for you", "liked_for": "real expertise", "complaints": "slow and costly", "url": ""},
        {"name": "Spreadsheet + survey tool", "maker": "DIY", "price": "$0-30/month", "pitch": "What most small teams do today", "liked_for": "cheap and flexible", "complaints": "manual, error-prone", "url": ""},
        {"name": "Well-funded startup", "maker": "VC-backed", "price": "$99/month", "pitch": "Modern, AI-first take on the problem", "liked_for": "slick product", "complaints": "unproven, may pivot", "url": ""},
    ],
    "news": [
        {"headline": "Budgets tighten for new software tools", "source": "Simulated Business", "date": "2026", "gist": "Teams consolidate tools and cut experiments.", "url": "", "tone": "negative"},
        {"headline": "AI tools win over small teams", "source": "Simulated Tech", "date": "2026", "gist": "Adoption of AI-first tools keeps rising among startups.", "url": "", "tone": "positive"},
    ],
    "buyer_complaints": ["hard to prove ROI", "another tool to learn", "pricing that scales too fast"],
    "substitutes": ["doing it by hand", "asking a few customers directly"],
}
FAKE_MARKET: dict[str, dict] = {"creative": _PRODUCT_MARKET, "website": _PRODUCT_MARKET, "offer": _PRODUCT_MARKET, "idea": _IDEA_MARKET}
