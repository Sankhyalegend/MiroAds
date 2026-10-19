"""The stratification frame: every dimension a persona is sampled on, with population weights.
The frame is the part that must be designed, not randomized. Randomness goes into texture (generate.py)
and into the per-run draw (sampler.py)."""
from __future__ import annotations

import random
from typing import Any

PROFESSION_GROUPS = ["Engineering", "Design", "Marketing", "Finance", "Operations", "Healthcare", "Education", "Retail & Service", "Students", "Executives"]
PROFESSIONS = {
    "Engineering": ["Backend developer", "Frontend developer", "Data engineer", "DevOps engineer", "ML engineer", "QA engineer", "Hardware engineer", "Embedded engineer"],
    "Design": ["UX designer", "Product designer", "Graphic designer", "Brand designer", "Motion designer", "Industrial designer"],
    "Marketing": ["Growth marketer", "Content strategist", "Performance marketer", "Brand manager", "SEO specialist", "Community manager", "PR manager"],
    "Finance": ["Financial analyst", "Accountant", "VC associate", "Procurement manager", "Controller", "Insurance underwriter"],
    "Operations": ["Operations manager", "Supply chain analyst", "Project manager", "Customer support lead", "Facilities manager"],
    "Healthcare": ["Nurse", "Physician", "Physiotherapist", "Pharmacist", "Sleep researcher", "Dentist"],
    "Education": ["Teacher", "Professor", "Tutor", "School administrator", "Librarian"],
    "Retail & Service": ["Store manager", "Barista", "Sales associate", "Restaurant owner", "Delivery driver", "Hairdresser", "Electrician"],
    "Students": ["CS student", "MBA student", "Design student", "Nursing student", "PhD candidate", "Law student"],
    "Executives": ["Startup founder", "CFO", "VP Marketing", "Head of Product", "Small business owner", "Agency owner"],
}

# Country, GDP tier, purchasing-power index (US=1.0), common currency cue.
COUNTRIES: list[tuple[str, str, float, str]] = [
    ("United States", "high", 1.00, "$"), ("United Kingdom", "high", 0.85, "£"), ("Germany", "high", 0.90, "€"),
    ("Canada", "high", 0.85, "C$"), ("Australia", "high", 0.88, "A$"), ("Singapore", "high", 0.95, "S$"),
    ("Japan", "high", 0.75, "¥"), ("South Korea", "high", 0.70, "₩"), ("UAE", "high", 0.90, "AED"),
    ("Brazil", "upper-middle", 0.35, "R$"), ("Mexico", "upper-middle", 0.35, "MX$"), ("Turkey", "upper-middle", 0.30, "₺"),
    ("China", "upper-middle", 0.40, "¥"), ("South Africa", "upper-middle", 0.30, "R"), ("Poland", "upper-middle", 0.50, "zł"),
    ("India", "lower-middle", 0.18, "₹"), ("Indonesia", "lower-middle", 0.20, "Rp"), ("Philippines", "lower-middle", 0.18, "₱"),
    ("Vietnam", "lower-middle", 0.18, "₫"), ("Egypt", "lower-middle", 0.15, "E£"), ("Nigeria", "lower-middle", 0.12, "₦"),
    ("Kenya", "lower-middle", 0.12, "KSh"), ("Bangladesh", "low", 0.10, "৳"), ("Pakistan", "low", 0.10, "₨"),
]
COUNTRY_W = [0.22, 0.07, 0.06, 0.04, 0.03, 0.02, 0.04, 0.03, 0.02, 0.05, 0.04, 0.02, 0.06, 0.02, 0.02, 0.12, 0.03, 0.02, 0.02, 0.02, 0.03, 0.01, 0.01, 0.01]

INCOME = ["Low", "Lower-middle", "Middle", "Upper-middle", "High"]          # relative to own country
INCOME_W = [0.18, 0.25, 0.30, 0.18, 0.09]
AGES = ["18-24", "25-34", "35-44", "45-54", "55+"]
AGE_W = [0.17, 0.29, 0.24, 0.17, 0.13]
IDEOLOGY = ["Progressive", "Moderate", "Conservative", "Libertarian"]
IDEOLOGY_W = [0.30, 0.36, 0.24, 0.10]
ECON = ["Frugal", "Value-seeking", "Premium"]
TECH = ["Innovator", "Early adopter", "Early majority", "Late majority", "Laggard"]
TECH_W = [0.04, 0.14, 0.34, 0.32, 0.16]
ROLES = ["Buyer", "User", "Influencer", "Gatekeeper", "Investor"]
ROLES_W = [0.46, 0.30, 0.09, 0.10, 0.05]
TRUST = ["Default-trusting", "Sceptical of marketing", "Sceptical of tech", "Burned before"]
TRUST_W = [0.30, 0.35, 0.15, 0.20]
HEURISTIC = ["Price-first", "Brand-first", "Reviews-first", "Spec-sheet reader", "Ask a friend", "Impulse", "Committee decision"]
HEURISTIC_W = [0.24, 0.12, 0.22, 0.12, 0.12, 0.10, 0.08]
DIET = ["Reddit", "YouTube reviews", "LinkedIn", "TikTok/Instagram", "Newspapers & podcasts", "Word of mouth", "Trade press"]
DIET_W = [0.16, 0.20, 0.12, 0.18, 0.12, 0.14, 0.08]
TEMPERAMENT = ["Optimistic", "Anxious", "Cynical", "Enthusiastic", "Pragmatic", "Contrarian"]
TEMPERAMENT_W = [0.20, 0.15, 0.18, 0.15, 0.22, 0.10]
INSTITUTION_TRUST = ["Trusts institutions", "Neutral", "Distrusts institutions"]
# What actually moves this person when they look at something new. The single biggest lever against
# "everyone demands a spec sheet": most people are not spec-sheet people.
MOTIVATION = ["Looks and aesthetics", "Status and how it reflects on me", "Convenience and less friction", "Saving money", "Health and wellbeing",
              "Novelty and being first", "What people I respect use", "Ethics and sustainability", "Reliability and not being let down", "Fun and delight",
              "Fitting into my routine", "Proof and measurements"]
MOTIVATION_W = [0.12, 0.07, 0.13, 0.13, 0.08, 0.06, 0.09, 0.05, 0.10, 0.06, 0.06, 0.05]
RESPONSE_STYLE = ["Gut reaction first, reasons later", "Weighs pros and cons out loud", "Compares to the last thing I bought", "Asks what friends would say",
                  "Pictures it in my own home or desk", "Looks for the catch", "Gets excited easily, cools down later", "Barely engages unless it is relevant to me"]
BIGTECH = ["Pro big tech", "Neutral on big tech", "Anti big tech"]
MOODS = ["rushed", "bored", "curious", "irritable", "upbeat", "tired", "focused", "distracted"]

FIRST = ["Aisha", "Ben", "Carla", "Dev", "Elena", "Farid", "Grace", "Hiro", "Ines", "Jonas", "Kavya", "Liam", "Maya", "Nikolai", "Olu", "Priya", "Quinn", "Rosa", "Sam", "Tariq", "Uma", "Victor", "Wen", "Xavier", "Yara", "Zoe", "Arjun", "Beatriz", "Chen", "Dana", "Emeka", "Freya", "Gabriel", "Hana", "Ivan", "Jade", "Kofi", "Lucia", "Mateo", "Noor", "Omar", "Pia", "Ravi", "Sofia", "Tomas", "Ulla", "Vikram", "Wei", "Yusuf", "Zara"]
LAST = ["Okafor", "Müller", "Sato", "Rodriguez", "Patel", "Nguyen", "Kowalski", "Haddad", "Silva", "Andersen", "Ivanova", "Mensah", "Rossi", "Khan", "Oyelaran", "Whitfield", "Alvarez", "Hoffmann", "Kim", "Raman", "Dubois", "Tanaka", "Novak", "Baptiste", "Costa", "Lindqvist", "Adeyemi", "Sharma", "Castro", "Yilmaz", "Park", "Santos", "Fischer", "Ibrahim", "Moreau", "Das"]


def pick(rng: random.Random, options: list, weights: list[float] | None = None):
    return rng.choices(options, weights=weights, k=1)[0]


def sample_skeleton(seed: int) -> dict[str, Any]:
    """One persona's structural attributes. Deterministic per seed."""
    rng = random.Random(seed)
    group = PROFESSION_GROUPS[seed % len(PROFESSION_GROUPS)]  # perfectly even coverage of groups
    country, gdp, ppp, currency = pick(rng, COUNTRIES, COUNTRY_W)
    age = pick(rng, AGES, [0.72, 0.24, 0.04, 0, 0]) if group == "Students" else pick(rng, AGES, AGE_W)
    income = pick(rng, INCOME, [0.6, 0.3, 0.1, 0, 0]) if group == "Students" else pick(rng, INCOME, INCOME_W)
    if group == "Executives":
        income = pick(rng, INCOME, [0.02, 0.08, 0.25, 0.40, 0.25])
    econ = {"Low": [0.65, 0.30, 0.05], "Lower-middle": [0.45, 0.45, 0.10], "Middle": [0.25, 0.55, 0.20],
            "Upper-middle": [0.12, 0.50, 0.38], "High": [0.06, 0.34, 0.60]}[income]
    traits = {k: round(rng.random(), 2) for k in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")}
    temperament = pick(rng, TEMPERAMENT, TEMPERAMENT_W)
    if traits["agreeableness"] < 0.25 and traits["openness"] > 0.6:
        temperament = "Contrarian"
    influence = round(min(1.0, (rng.random() ** 3) * 1.6 + rng.random() * 0.08), 3)
    tech = pick(rng, TECH, TECH_W)
    if group in ("Engineering", "Design") and rng.random() < 0.6:
        tech = pick(rng, TECH, [0.12, 0.38, 0.35, 0.12, 0.03])
    return {
        "seed": seed,
        "professionGroup": group,
        "profession": pick(rng, PROFESSIONS[group]),
        "ageBand": age,
        "country": country, "gdpTier": gdp, "purchasingPower": ppp, "currency": currency,
        "income": income,                          # relative to own country
        "ideology": pick(rng, IDEOLOGY, IDEOLOGY_W),
        "economic": pick(rng, ECON, econ),
        "tech": tech,
        "role": pick(rng, ROLES, ROLES_W),
        "trust": pick(rng, TRUST, TRUST_W),
        "heuristic": pick(rng, HEURISTIC, HEURISTIC_W),
        "diet": pick(rng, DIET, DIET_W),
        "temperament": temperament,
        "motivation": pick(rng, MOTIVATION, MOTIVATION_W),
        "responseStyle": pick(rng, RESPONSE_STYLE),
        "institutions": pick(rng, INSTITUTION_TRUST, [0.35, 0.40, 0.25]),
        "bigTech": pick(rng, BIGTECH, [0.30, 0.45, 0.25]),
        "traits": traits,
        "influence": influence,
        "activity": round(0.2 + rng.random() * 0.8, 2),
        "gender": pick(rng, ["woman", "man", "non-binary"], [0.49, 0.49, 0.02]),
        "nameHint": f"{pick(rng, FIRST)} {pick(rng, LAST)}",
    }


def to_frontend_persona(agent_id: int, persona_id: int, sk: dict, profile: dict, mood: str) -> dict:
    """The shape the frontend's Persona type expects, plus extras the detail panel can show."""
    return {
        "id": agent_id,
        "personaId": persona_id,
        "name": profile.get("name") or sk["nameHint"],
        "profession": sk["profession"],
        "professionGroup": sk["professionGroup"],
        "ageBand": sk["ageBand"],
        "income": sk["income"],
        "ideology": sk["ideology"],
        "economic": sk["economic"],
        "tech": sk["tech"],
        "region": sk["country"],
        "role": sk["role"],
        "traits": sk["traits"],
        "influence": sk["influence"],
        "activity": sk["activity"],
        "mood": mood,
        "extra": {
            "country": sk["country"], "gdpTier": sk["gdpTier"], "purchasingPower": sk["purchasingPower"], "currency": sk["currency"],
            "trust": sk["trust"], "heuristic": sk["heuristic"], "diet": sk["diet"], "temperament": sk["temperament"],
            "motivation": sk.get("motivation", ""), "responseStyle": sk.get("responseStyle", ""),
            "institutions": sk["institutions"], "bigTech": sk["bigTech"],
            "backstory": profile.get("backstory", ""), "petPeeves": profile.get("pet_peeves", []),
            "overvalues": profile.get("overvalues", ""), "ignores": profile.get("ignores", ""),
            "voice": profile.get("voice", ""), "pastProducts": profile.get("past_products", []),
            "lens": profile.get("evaluation_lens", ""),
        },
    }


def persona_card(sk: dict, profile: dict, mood: str) -> str:
    """Compact text card used in every prompt for this agent."""
    pp = "; ".join(f"{p.get('name')}: {p.get('verdict')}" for p in profile.get("past_products", [])[:2])
    return (
        f"You are {profile.get('name') or sk['nameHint']}, a {sk['ageBand']}-year-old {sk['gender']} {sk['profession'].lower()} in {sk['country']} "
        f"({sk['gdpTier']}-income country, local purchasing power {sk['purchasingPower']:.2f}x US; your household is {sk['income'].lower()} income there; prices in {sk['currency']} feel normal to you).\n"
        f"Politics: {sk['ideology']}. Spending: {sk['economic']}. Tech: {sk['tech']}. Role when buying: {sk['role']}. Trust posture: {sk['trust']}. "
        f"How you decide: {sk['heuristic']}. What moves you most: {sk.get('motivation', 'varies')}. How you react to new things: {sk.get('responseStyle', 'varies')}. "
        f"Where you get information: {sk['diet']}. Temperament: {sk['temperament']}; {sk['institutions']}; {sk['bigTech']}.\n"
        f"Personality (0-1): openness {sk['traits']['openness']}, conscientiousness {sk['traits']['conscientiousness']}, extraversion {sk['traits']['extraversion']}, agreeableness {sk['traits']['agreeableness']}, neuroticism {sk['traits']['neuroticism']}.\n"
        f"Backstory: {profile.get('backstory', '')}\n"
        f"Pet peeves: {'; '.join(profile.get('pet_peeves', []))}. You overvalue {profile.get('overvalues', '')} and ignore {profile.get('ignores', '')}.\n"
        f"Past products: {pp}.\n"
        f"How you evaluate things: {profile.get('evaluation_lens', '')}\n"
        f"Writing voice: {profile.get('voice', '')}\n"
        f"Today you feel {mood}.\n"
        f"You are a whole person, not a checklist: your taste, mood, situation and what moves you matter as much as your rules. "
        f"Some things you simply like or dislike without needing documents."
    )
