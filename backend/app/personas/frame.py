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

INCOME = ["Low", "Lower-middle", "Middle", "Upper-middle", "High"]          # relative to own country; weights in INCOME_BY_GROUP
AGES = ["18-24", "25-34", "35-44", "45-54", "55+"]                          # weights in AGE_BY_GROUP
IDEOLOGY = ["Progressive", "Moderate", "Conservative", "Libertarian"]
IDEOLOGY_W = [0.30, 0.36, 0.24, 0.10]
ECON = ["Frugal", "Value-seeking", "Premium"]
TECH = ["Innovator", "Early adopter", "Early majority", "Late majority", "Laggard"]  # weights in TECH_BY_AGE
ROLES = ["Buyer", "User", "Influencer", "Gatekeeper", "Investor"]
ROLES_W = [0.46, 0.30, 0.09, 0.10, 0.05]
TRUST = ["Default-trusting", "Sceptical of marketing", "Sceptical of tech", "Burned before"]
TRUST_W = [0.30, 0.35, 0.15, 0.20]
HEURISTIC = ["Price-first", "Brand-first", "Reviews-first", "Spec-sheet reader", "Ask a friend", "Impulse", "Committee decision"]
HEURISTIC_W = [0.24, 0.12, 0.22, 0.12, 0.12, 0.10, 0.08]
DIET = ["Reddit", "YouTube reviews", "LinkedIn", "TikTok/Instagram", "Newspapers & podcasts", "Word of mouth", "Trade press"]  # weights in DIET_BY_AGE
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
# Never drawn at random: only the news an agent saw in the market scan can put them in these (engine/market.py).
NEWS_MOODS = ["wary", "excited"]

FIRST = ["Aisha", "Ben", "Carla", "Dev", "Elena", "Farid", "Grace", "Hiro", "Ines", "Jonas", "Kavya", "Liam", "Maya", "Nikolai", "Olu", "Priya", "Quinn", "Rosa", "Sam", "Tariq", "Uma", "Victor", "Wen", "Xavier", "Yara", "Zoe", "Arjun", "Beatriz", "Chen", "Dana", "Emeka", "Freya", "Gabriel", "Hana", "Ivan", "Jade", "Kofi", "Lucia", "Mateo", "Noor", "Omar", "Pia", "Ravi", "Sofia", "Tomas", "Ulla", "Vikram", "Wei", "Yusuf", "Zara"]
LAST = ["Okafor", "Müller", "Sato", "Rodriguez", "Patel", "Nguyen", "Kowalski", "Haddad", "Silva", "Andersen", "Ivanova", "Mensah", "Rossi", "Khan", "Oyelaran", "Whitfield", "Alvarez", "Hoffmann", "Kim", "Raman", "Dubois", "Tanaka", "Novak", "Baptiste", "Costa", "Lindqvist", "Adeyemi", "Sharma", "Castro", "Yilmaz", "Park", "Santos", "Fischer", "Ibrahim", "Moreau", "Das"]

# ---- Version 2: linked traits and buying traits. Approximate real-world shares, written as plain constants. ----
# Stored on every persona as "v". New runs sample only the current version; old reports keep their own copies of their people.
FRAME_VERSION = 2

# Age band weights (AGES order) by profession group: students are young, executives older.
AGE_BY_GROUP = {
    "Students": [0.70, 0.25, 0.04, 0.01, 0.00], "Executives": [0.02, 0.18, 0.32, 0.28, 0.20],
    "Engineering": [0.10, 0.42, 0.28, 0.14, 0.06], "Design": [0.12, 0.42, 0.27, 0.13, 0.06],
    "Marketing": [0.12, 0.40, 0.27, 0.14, 0.07], "Finance": [0.06, 0.30, 0.30, 0.21, 0.13],
    "Operations": [0.07, 0.28, 0.29, 0.22, 0.14], "Healthcare": [0.06, 0.27, 0.27, 0.22, 0.18],
    "Education": [0.05, 0.24, 0.27, 0.23, 0.21], "Retail & Service": [0.22, 0.30, 0.21, 0.15, 0.12],
}
# Job weights within a group where real numbers are lopsided (nurses outnumber physicians; most owners run small businesses).
# Groups not listed pick jobs evenly.
JOB_W = {
    "Healthcare": {"Nurse": 0.42, "Physician": 0.16, "Physiotherapist": 0.12, "Pharmacist": 0.12, "Sleep researcher": 0.04, "Dentist": 0.08},
    "Education": {"Teacher": 0.55, "Professor": 0.12, "Tutor": 0.15, "School administrator": 0.10, "Librarian": 0.08},
    "Retail & Service": {"Store manager": 0.12, "Barista": 0.12, "Sales associate": 0.22, "Restaurant owner": 0.08, "Delivery driver": 0.18, "Hairdresser": 0.12, "Electrician": 0.16},
    "Executives": {"Startup founder": 0.15, "CFO": 0.08, "VP Marketing": 0.08, "Head of Product": 0.10, "Small business owner": 0.45, "Agency owner": 0.14},
    "Students": {"CS student": 0.22, "MBA student": 0.10, "Design student": 0.12, "Nursing student": 0.18, "PhD candidate": 0.10, "Law student": 0.15},
}
# Youngest age band (index into AGES) for jobs that take years of training or seniority. No 19-year-old CFOs.
MIN_AGE_BAND = {"Physician": 1, "Dentist": 1, "Pharmacist": 1, "Professor": 1, "Sleep researcher": 1, "School administrator": 1,
                "PhD candidate": 1, "MBA student": 1, "Controller": 1, "VP Marketing": 1, "Head of Product": 1, "Agency owner": 1, "CFO": 2}
# Household income band weights (INCOME order, relative to own country) by group, then tilted by age band: pay rises with seniority.
INCOME_BY_GROUP = {
    "Students": [0.55, 0.30, 0.12, 0.03, 0.00], "Executives": [0.02, 0.06, 0.22, 0.40, 0.30],
    "Engineering": [0.03, 0.10, 0.32, 0.38, 0.17], "Design": [0.06, 0.18, 0.40, 0.27, 0.09],
    "Marketing": [0.05, 0.16, 0.39, 0.29, 0.11], "Finance": [0.03, 0.12, 0.35, 0.34, 0.16],
    "Operations": [0.07, 0.22, 0.42, 0.23, 0.06], "Healthcare": [0.05, 0.17, 0.38, 0.28, 0.12],
    "Education": [0.08, 0.27, 0.45, 0.17, 0.03], "Retail & Service": [0.28, 0.35, 0.27, 0.08, 0.02],
}
INCOME_AGE_TILT = [[1.6, 1.3, 0.8, 0.5, 0.3], [1.1, 1.1, 1.0, 0.9, 0.7], [0.9, 0.95, 1.0, 1.1, 1.15], [0.85, 0.9, 1.0, 1.1, 1.25], [1.0, 1.0, 1.0, 1.0, 1.0]]
# Jobs that pay a step above or below the rest of their group. Retirement takes a step off too.
INCOME_STEP = {"Physician": 1, "Dentist": 1, "Pharmacist": 1, "CFO": 1, "VC associate": 1, "Electrician": 1, "Barista": -1, "Delivery driver": -1}
EDUCATION = ["Secondary school", "Vocational or trade", "Some university", "Bachelor's degree", "Master's or higher"]
EDU_BY_GROUP = {
    "Students": [0.00, 0.05, 0.75, 0.12, 0.08], "Executives": [0.08, 0.07, 0.15, 0.40, 0.30],
    "Engineering": [0.02, 0.05, 0.10, 0.55, 0.28], "Design": [0.03, 0.12, 0.15, 0.55, 0.15],
    "Marketing": [0.03, 0.04, 0.13, 0.58, 0.22], "Finance": [0.02, 0.03, 0.08, 0.55, 0.32],
    "Operations": [0.12, 0.12, 0.20, 0.42, 0.14], "Healthcare": [0.02, 0.30, 0.08, 0.50, 0.10],  # nurses, physios; doctors are in EDU_BY_JOB
    "Education": [0.02, 0.03, 0.08, 0.45, 0.42], "Retail & Service": [0.38, 0.28, 0.20, 0.12, 0.02],
}
EDU_BY_JOB = {"Physician": 4, "Dentist": 4, "Pharmacist": 4, "Professor": 4, "Sleep researcher": 4, "PhD candidate": 4, "MBA student": 3, "Electrician": 1, "Hairdresser": 1}
SETTLEMENT = ["City", "Suburb", "Small town or countryside"]
SETTLEMENT_BY_COUNTRY = {
    "United States": [0.31, 0.52, 0.17], "United Kingdom": [0.35, 0.45, 0.20], "Germany": [0.32, 0.38, 0.30], "Canada": [0.35, 0.45, 0.20],
    "Australia": [0.40, 0.45, 0.15], "Singapore": [1.00, 0.00, 0.00], "Japan": [0.50, 0.35, 0.15], "South Korea": [0.55, 0.30, 0.15],
    "UAE": [0.75, 0.20, 0.05], "Brazil": [0.50, 0.30, 0.20], "Mexico": [0.48, 0.28, 0.24], "Turkey": [0.50, 0.25, 0.25],
    "China": [0.45, 0.20, 0.35], "South Africa": [0.45, 0.20, 0.35], "Poland": [0.40, 0.20, 0.40], "India": [0.30, 0.10, 0.60],
    "Indonesia": [0.40, 0.15, 0.45], "Philippines": [0.35, 0.15, 0.50], "Vietnam": [0.30, 0.10, 0.60], "Egypt": [0.38, 0.07, 0.55],
    "Nigeria": [0.40, 0.10, 0.50], "Kenya": [0.25, 0.08, 0.67], "Bangladesh": [0.30, 0.08, 0.62], "Pakistan": [0.33, 0.07, 0.60],
}
OFFICE_GROUPS = ("Engineering", "Design", "Marketing", "Finance", "Executives", "Students")  # these jobs cluster in cities
LIFE_STAGES = ["Student", "Single", "Couple, no kids", "Parent of young kids", "Parent of teens", "Empty nester", "Retired"]
LIFE_BY_AGE = [  # LIFE_STAGES weights by age band. "Student" comes only from the Students group.
    [0.00, 0.68, 0.20, 0.12, 0.00, 0.00, 0.00],
    [0.00, 0.36, 0.30, 0.32, 0.02, 0.00, 0.00],
    [0.00, 0.17, 0.18, 0.40, 0.25, 0.00, 0.00],
    [0.00, 0.14, 0.12, 0.08, 0.38, 0.28, 0.00],
    [0.00, 0.12, 0.08, 0.02, 0.08, 0.38, 0.32],
]
HOUSEHOLD = {  # people living in the household: (sizes, weights) by life stage
    "Student": ([1, 2, 3, 4, 5], [0.25, 0.20, 0.25, 0.20, 0.10]), "Single": ([1, 2, 3, 4], [0.55, 0.20, 0.15, 0.10]),
    "Couple, no kids": ([2, 3], [0.85, 0.15]), "Parent of young kids": ([3, 4, 5, 6], [0.35, 0.40, 0.17, 0.08]),
    "Parent of teens": ([3, 4, 5, 6], [0.25, 0.40, 0.25, 0.10]), "Empty nester": ([1, 2, 3], [0.15, 0.75, 0.10]),
    "Retired": ([1, 2, 3], [0.30, 0.60, 0.10]),
}
# Rough money left each month after rent, food and bills for a US household in each income band (USD); scaled by country and household.
SPARE_USD = [60, 180, 400, 900, 2200]
SPARE_BY_STAGE = {"Student": 0.6, "Single": 1.1, "Couple, no kids": 1.15, "Parent of young kids": 0.7, "Parent of teens": 0.8, "Empty nester": 1.25, "Retired": 0.9}
# Approximate local currency units per US dollar (2026), so spare money reads in the person's own money.
FX = {"United States": 1, "United Kingdom": 0.78, "Germany": 0.90, "Canada": 1.38, "Australia": 1.52, "Singapore": 1.33, "Japan": 150,
      "South Korea": 1380, "UAE": 3.67, "Brazil": 5.5, "Mexico": 18.5, "Turkey": 45, "China": 7.2, "South Africa": 18, "Poland": 3.9,
      "India": 87, "Indonesia": 16300, "Philippines": 57, "Vietnam": 25500, "Egypt": 49, "Nigeria": 1550, "Kenya": 129, "Bangladesh": 121, "Pakistan": 282}
TECH_BY_AGE = [[0.06, 0.20, 0.38, 0.28, 0.08], [0.05, 0.18, 0.37, 0.30, 0.10], [0.04, 0.14, 0.36, 0.32, 0.14], [0.03, 0.10, 0.32, 0.36, 0.19], [0.02, 0.06, 0.26, 0.38, 0.28]]
DIET_BY_AGE = [  # DIET weights by age band
    [0.20, 0.22, 0.04, 0.34, 0.06, 0.12, 0.02],
    [0.19, 0.22, 0.12, 0.22, 0.10, 0.11, 0.04],
    [0.14, 0.21, 0.15, 0.14, 0.14, 0.14, 0.08],
    [0.10, 0.19, 0.14, 0.10, 0.20, 0.17, 0.10],
    [0.06, 0.16, 0.08, 0.07, 0.28, 0.27, 0.08],
]
IDEOLOGY_AGE_TILT = [[1.4, 0.9, 0.7, 1.1], [1.2, 1.0, 0.8, 1.1], [1.0, 1.0, 1.0, 1.0], [0.85, 1.0, 1.2, 0.95], [0.75, 1.0, 1.4, 0.8]]
GENDER_BY_GROUP = {"Engineering": [0.27, 0.71, 0.02], "Healthcare": [0.68, 0.31, 0.01], "Education": [0.66, 0.33, 0.01], "Executives": [0.33, 0.66, 0.01]}
ROLES_BY_GROUP = {"Executives": [0.30, 0.15, 0.10, 0.25, 0.20], "Students": [0.40, 0.45, 0.12, 0.02, 0.01]}
AD_RECEPTIVITY = ["Ignores most ads", "Sceptical of ads", "Clicks if it's relevant", "Enjoys discovering things through ads"]
ADBLOCK_BY_TECH = {"Innovator": 0.55, "Early adopter": 0.48, "Early majority": 0.32, "Late majority": 0.18, "Laggard": 0.07}
AD_PLACES = ["Instagram or TikTok feed", "Facebook feed", "YouTube ads", "Reddit promoted posts", "LinkedIn feed", "News websites", "Podcasts",
             "TV and streaming", "Search results", "WhatsApp or group chats", "Billboards and transit", "Trade magazines", "In shops"]
AD_PLACES_BY_AGE = [  # AD_PLACES weights by age band: where else someone meets ads, besides their main information source
    [0.30, 0.04, 0.22, 0.08, 0.02, 0.03, 0.06, 0.06, 0.08, 0.05, 0.04, 0.00, 0.02],
    [0.20, 0.08, 0.18, 0.07, 0.07, 0.06, 0.08, 0.08, 0.08, 0.05, 0.03, 0.00, 0.02],
    [0.12, 0.15, 0.15, 0.04, 0.08, 0.09, 0.07, 0.12, 0.08, 0.05, 0.03, 0.00, 0.02],
    [0.07, 0.20, 0.13, 0.02, 0.07, 0.12, 0.05, 0.17, 0.08, 0.05, 0.02, 0.00, 0.02],
    [0.03, 0.22, 0.10, 0.01, 0.03, 0.15, 0.04, 0.25, 0.08, 0.05, 0.02, 0.00, 0.02],
]
PLACE_BY_DIET = {"Reddit": "Reddit promoted posts", "YouTube reviews": "YouTube ads", "LinkedIn": "LinkedIn feed",
                 "TikTok/Instagram": "Instagram or TikTok feed", "Trade press": "Trade magazines"}
# Countries where group chats are a main way word about products spreads.
CHAT_COUNTRIES = {"India", "Brazil", "Mexico", "Indonesia", "Nigeria", "Kenya", "South Africa", "Egypt", "Pakistan", "Bangladesh", "Turkey", "Philippines", "Vietnam"}
VALUES = ["Privacy", "Sustainability", "Local-made", "Status", "Value for money", "Convenience"]
VALUE_BY_MOTIVATION = {"Status and how it reflects on me": "Status", "Ethics and sustainability": "Sustainability",
                       "Saving money": "Value for money", "Convenience and less friction": "Convenience"}
BRAND_LOYALTY = ["Loyal to brands they trust", "Switches for a better deal", "Likes trying new brands"]


def pick(rng: random.Random, options: list, weights: list[float] | None = None):
    return rng.choices(options, weights=weights, k=1)[0]


def _tilt(weights: list[float], factors: list[float]) -> list[float]:
    return [w * f for w, f in zip(weights, factors)]


def _step(options: list, value: Any, step: int) -> Any:
    return options[min(max(options.index(value) + step, 0), len(options) - 1)]


def _round2(x: float) -> int:
    """Two significant figures, so amounts read like something a person would say."""
    if x < 10:
        return max(1, round(x))
    mag = 10 ** (len(str(int(x))) - 2)
    return int(round(x / mag) * mag)


def money(currency: str, amount: int) -> str:
    return f"{currency}{' ' if currency.isalpha() and len(currency) > 1 else ''}{amount:,}"


def sample_skeleton(seed: int) -> dict[str, Any]:
    """One persona's attributes, deterministic per seed. Traits are linked the way they are in life: age follows the job,
    income follows job and age, life stage and household follow age, spare money follows country, income and household,
    and how someone meets and treats ads follows their age, tech habits and trust."""
    rng = random.Random(seed)
    group = PROFESSION_GROUPS[seed % len(PROFESSION_GROUPS)]  # perfectly even coverage of groups
    country, gdp, ppp, currency = pick(rng, COUNTRIES, COUNTRY_W)
    age_i = AGES.index(pick(rng, AGES, AGE_BY_GROUP[group]))
    jobs = [j for j in PROFESSIONS[group] if MIN_AGE_BAND.get(j, 0) <= age_i] or PROFESSIONS[group]
    profession = pick(rng, jobs, [JOB_W[group][j] for j in jobs] if group in JOB_W else None)
    stage = "Student" if group == "Students" and rng.random() < 0.85 else pick(rng, LIFE_STAGES, LIFE_BY_AGE[age_i])
    sizes, size_w = HOUSEHOLD[stage]
    household = pick(rng, sizes, size_w)
    if gdp in ("lower-middle", "low") and rng.random() < 0.4:
        household += rng.choice([1, 2])  # extended family under one roof
    income = pick(rng, INCOME, _tilt(INCOME_BY_GROUP[group], INCOME_AGE_TILT[age_i]))
    income = _step(INCOME, income, INCOME_STEP.get(profession, 0) - (1 if stage == "Retired" else 0))
    econ = {"Low": [0.65, 0.30, 0.05], "Lower-middle": [0.45, 0.45, 0.10], "Middle": [0.25, 0.55, 0.20],
            "Upper-middle": [0.12, 0.50, 0.38], "High": [0.06, 0.34, 0.60]}[income]
    spare_usd = SPARE_USD[INCOME.index(income)] * ppp * SPARE_BY_STAGE[stage] * rng.uniform(0.6, 1.5)
    settle_w = SETTLEMENT_BY_COUNTRY[country]
    if group in OFFICE_GROUPS:
        settle_w = _tilt(settle_w, [2.0, 1.3, 0.4])
    traits = {k: round(rng.random(), 2) for k in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")}
    temperament = pick(rng, TEMPERAMENT, TEMPERAMENT_W)
    if traits["agreeableness"] < 0.25 and traits["openness"] > 0.6:
        temperament = "Contrarian"
    influence = round(min(1.0, (rng.random() ** 3) * 1.6 + rng.random() * 0.08), 3)
    tech = pick(rng, TECH, TECH_BY_AGE[age_i])
    if group in ("Engineering", "Design") and rng.random() < 0.6:
        tech = pick(rng, TECH, [0.12, 0.38, 0.35, 0.12, 0.03])
    diet_w = list(DIET_BY_AGE[age_i])
    if group in ("Students", "Retail & Service"):
        diet_w[2] *= 0.3; diet_w[6] *= 0.3  # LinkedIn, trade press
    elif group == "Executives":
        diet_w[2] *= 1.6; diet_w[6] *= 1.5
    diet = pick(rng, DIET, diet_w)
    ideology = pick(rng, IDEOLOGY, _tilt(IDEOLOGY_W, IDEOLOGY_AGE_TILT[age_i]))
    trust = pick(rng, TRUST, TRUST_W)
    heuristic_w = list(HEURISTIC_W)
    if group in ("Students", "Retail & Service") or stage == "Retired":
        heuristic_w[6] *= 0.2  # few of them buy by committee
    heuristic = pick(rng, HEURISTIC, heuristic_w)
    motivation = pick(rng, MOTIVATION, MOTIVATION_W)
    big_tech = pick(rng, BIGTECH, [0.30, 0.45, 0.25])

    # How they meet and treat ads.
    if trust in ("Sceptical of marketing", "Burned before"):
        ad_w = [0.33, 0.47, 0.16, 0.04]
    elif tech in ("Innovator", "Early adopter") or motivation == "Novelty and being first":
        ad_w = [0.22, 0.20, 0.36, 0.22]
    else:
        ad_w = [0.35, 0.28, 0.27, 0.10]
    if age_i == 0:
        ad_w[3] *= 1.4
    ad_blocker = rng.random() < min(0.85, ADBLOCK_BY_TECH[tech] * (1.4 if group == "Engineering" else 1.0) * (0.6 if age_i == 4 else 1.0))
    if diet == "Newspapers & podcasts":
        main_place = "Podcasts" if ad_blocker or rng.random() < 0.5 else "News websites"
    elif diet == "Word of mouth":
        main_place = "WhatsApp or group chats" if country in CHAT_COUNTRIES else pick(rng, ["In shops", "TV and streaming"])
    else:
        main_place = PLACE_BY_DIET[diet]
    place_w = dict(zip(AD_PLACES, AD_PLACES_BY_AGE[age_i]))
    if group in ("Students", "Retail & Service") or stage == "Retired":
        place_w["LinkedIn feed"] *= 0.2
    if country in CHAT_COUNTRIES:
        place_w["WhatsApp or group chats"] *= 3
    if ad_blocker:
        place_w["News websites"] *= 0.1  # banners are blocked; apps, video and the street are not
    places = [main_place]
    for _ in range(rng.choice([1, 2])):
        places.append(pick(rng, AD_PLACES, [0 if p in places else place_w[p] for p in AD_PLACES]))

    # Two things they care about when buying, and how attached they are to brands.
    value_w = dict(zip(VALUES, [1.0, 1.0, 0.8, 0.6, 1.4, 1.3]))
    for cond, value, f in ((ideology == "Progressive", "Sustainability", 2), (ideology == "Conservative", "Local-made", 1.8),
                           (ideology == "Libertarian", "Privacy", 2), (big_tech == "Anti big tech", "Privacy", 2),
                           (income in ("Low", "Lower-middle"), "Value for money", 2), (income in ("Upper-middle", "High"), "Status", 1.5),
                           (income in ("Upper-middle", "High"), "Convenience", 1.4), (stage == "Parent of young kids", "Convenience", 1.5),
                           (motivation in VALUE_BY_MOTIVATION, VALUE_BY_MOTIVATION.get(motivation), 3)):
        if cond:
            value_w[value] *= f
    first = pick(rng, VALUES, [value_w[v] for v in VALUES])
    values = [first, pick(rng, VALUES, [0 if v == first else value_w[v] for v in VALUES])]
    brand_w = [0.40, 0.40, 0.20]
    if heuristic == "Brand-first":
        brand_w[0] *= 2.5
    if heuristic == "Price-first":
        brand_w[1] *= 2
    if tech in ("Innovator", "Early adopter"):
        brand_w[2] *= 2
    if age_i == 4:
        brand_w[0] *= 1.5
    elif age_i == 0:
        brand_w[2] *= 1.4

    return {
        "v": FRAME_VERSION,
        "seed": seed,
        "professionGroup": group,
        "profession": profession,
        "ageBand": AGES[age_i],
        "gender": pick(rng, ["woman", "man", "non-binary"], GENDER_BY_GROUP.get(group, [0.49, 0.49, 0.02])),
        "country": country, "gdpTier": gdp, "purchasingPower": ppp, "currency": currency,
        "settlement": pick(rng, SETTLEMENT, settle_w),
        "lifeStage": stage,
        "household": household,
        "education": EDUCATION[EDU_BY_JOB[profession]] if profession in EDU_BY_JOB else pick(rng, EDUCATION, EDU_BY_GROUP[group]),
        "income": income,                          # relative to own country
        "spareMoney": money(currency, _round2(spare_usd * FX[country])),  # a month, after essentials, in their own currency
        "spareUsd": _round2(spare_usd),
        "ideology": ideology,
        "economic": pick(rng, ECON, econ),
        "tech": tech,
        "role": pick(rng, ROLES, ROLES_BY_GROUP.get(group, ROLES_W)),
        "trust": trust,
        "heuristic": heuristic,
        "diet": diet,
        "adReceptivity": pick(rng, AD_RECEPTIVITY, ad_w),
        "adBlocker": ad_blocker,
        "adPlaces": places,
        "values": values,
        "brandLoyalty": pick(rng, BRAND_LOYALTY, brand_w),
        "temperament": temperament,
        "motivation": motivation,
        "responseStyle": pick(rng, RESPONSE_STYLE),
        "institutions": pick(rng, INSTITUTION_TRUST, [0.35, 0.40, 0.25]),
        "bigTech": big_tech,
        "traits": traits,
        "influence": influence,
        "activity": round(0.2 + rng.random() * 0.8, 2),
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
            # Version 2 traits; absent on people from the first library.
            **{k: sk[k] for k in ("lifeStage", "household", "settlement", "education", "spareMoney", "adReceptivity", "adBlocker", "adPlaces", "values", "brandLoyalty") if k in sk},
        },
    }


SETTLEMENT_PHRASE = {"City": "in a city", "Suburb": "in the suburbs", "Small town or countryside": "in a small town or the countryside"}
AD_PHRASE = {"Ignores most ads": "you ignore most ads", "Sceptical of ads": "you are sceptical of ads",
             "Clicks if it's relevant": "you click when an ad is relevant to you", "Enjoys discovering things through ads": "you enjoy discovering things through ads"}


def _job(sk: dict) -> str:
    return f"retired {sk['profession'].lower()}" if sk.get("lifeStage") == "Retired" else sk["profession"].lower()


def _life_lines(sk: dict) -> str:
    """Household, money and ad habits (version 2 people only)."""
    if "lifeStage" not in sk:
        return ""
    return (
        f"Life: {sk['lifeStage'].lower()}, household of {sk['household']}, living {SETTLEMENT_PHRASE[sk['settlement']]}. Education: {sk['education']}. "
        f"Money left each month after rent, food and bills: about {sk['spareMoney']}.\n"
        f"Ads: {AD_PHRASE[sk['adReceptivity']]}; {'you use an ad blocker' if sk['adBlocker'] else 'no ad blocker'}; "
        f"you mostly meet ads on {', '.join(sk['adPlaces'])}. You care about {sk['values'][0].lower()} and {sk['values'][1].lower()}. "
        f"Brands: {sk['brandLoyalty'].lower()}.\n"
    )


def persona_card(sk: dict, profile: dict, mood: str, mood_reason: str = "") -> str:
    """Compact text card used in every prompt for this agent."""
    pp = "; ".join(f"{p.get('name')}: {p.get('verdict')}" for p in profile.get("past_products", [])[:2])
    return (
        f"You are {profile.get('name') or sk['nameHint']}, a {sk['ageBand']}-year-old {sk['gender']} {_job(sk)} in {sk['country']} "
        f"({sk['gdpTier']}-income country, local purchasing power {sk['purchasingPower']:.2f}x US; your household is {sk['income'].lower()} income there; prices in {sk['currency']} feel normal to you).\n"
        f"{_life_lines(sk)}"
        f"Politics: {sk['ideology']}. Spending: {sk['economic']}. Tech: {sk['tech']}. Role when buying: {sk['role']}. Trust posture: {sk['trust']}. "
        f"How you decide: {sk['heuristic']}. What moves you most: {sk.get('motivation', 'varies')}. How you react to new things: {sk.get('responseStyle', 'varies')}. "
        f"Where you get information: {sk['diet']}. Temperament: {sk['temperament']}; {sk['institutions']}; {sk['bigTech']}.\n"
        f"Personality (0-1): openness {sk['traits']['openness']}, conscientiousness {sk['traits']['conscientiousness']}, extraversion {sk['traits']['extraversion']}, agreeableness {sk['traits']['agreeableness']}, neuroticism {sk['traits']['neuroticism']}.\n"
        f"Backstory: {profile.get('backstory', '')}\n"
        f"Pet peeves: {'; '.join(profile.get('pet_peeves', []))}. You overvalue {profile.get('overvalues', '')} and ignore {profile.get('ignores', '')}.\n"
        f"Past products: {pp}.\n"
        f"How you evaluate things: {profile.get('evaluation_lens', '')}\n"
        f"Writing voice: {profile.get('voice', '')}\n"
        f"Today you feel {mood}{f': {mood_reason}' if mood_reason else ''}.\n"
        f"You are a whole person, not a checklist: your taste, mood, situation and what moves you matter as much as your rules. "
        f"Some things you simply like or dislike without needing documents."
    )
