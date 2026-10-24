import type {
  Persona, ProfessionGroup, Ideology, EconomicStance, TechAdoption, IncomeBand, AgeBand, DecisionRole, Intent,
} from '../types'

// Deterministic PRNG so a crowd of N is the same crowd every time (good for A/B comparisons).
export function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export const PROFESSION_GROUPS: ProfessionGroup[] = [
  'Engineering', 'Design', 'Marketing', 'Finance', 'Operations',
  'Healthcare', 'Education', 'Retail & Service', 'Students', 'Executives',
]

const PROFESSIONS: Record<ProfessionGroup, string[]> = {
  Engineering: ['Backend developer', 'Frontend developer', 'Data engineer', 'DevOps engineer', 'ML engineer', 'QA engineer', 'Hardware engineer'],
  Design: ['UX designer', 'Product designer', 'Graphic designer', 'Brand designer', 'Motion designer'],
  Marketing: ['Growth marketer', 'Content strategist', 'Performance marketer', 'Brand manager', 'SEO specialist', 'Community manager'],
  Finance: ['Financial analyst', 'Accountant', 'VC associate', 'Procurement manager', 'Controller'],
  Operations: ['Operations manager', 'Supply chain analyst', 'Project manager', 'Customer support lead'],
  Healthcare: ['Nurse', 'Physician', 'Physiotherapist', 'Pharmacist', 'Sleep researcher'],
  Education: ['Teacher', 'Professor', 'Tutor', 'School administrator'],
  'Retail & Service': ['Store manager', 'Barista', 'Sales associate', 'Restaurant owner', 'Delivery driver'],
  Students: ['CS student', 'MBA student', 'Design student', 'Nursing student', 'PhD candidate'],
  Executives: ['Startup founder', 'CFO', 'VP Marketing', 'Head of Product', 'Small business owner'],
}

const IDEOLOGIES: Ideology[] = ['Progressive', 'Moderate', 'Conservative', 'Libertarian']
const ECON: EconomicStance[] = ['Frugal', 'Value-seeking', 'Premium']
const TECH: TechAdoption[] = ['Innovator', 'Early adopter', 'Early majority', 'Late majority', 'Laggard']
const TECH_W = [0.05, 0.15, 0.35, 0.3, 0.15]
const INCOME: IncomeBand[] = ['Low', 'Lower-middle', 'Middle', 'Upper-middle', 'High']
const INCOME_W = [0.15, 0.25, 0.3, 0.2, 0.1]
const AGES: AgeBand[] = ['18-24', '25-34', '35-44', '45-54', '55+']
const AGE_W = [0.18, 0.3, 0.24, 0.16, 0.12]
const ROLES: DecisionRole[] = ['Buyer', 'User', 'Influencer', 'Gatekeeper', 'Investor']
const ROLE_W = [0.45, 0.3, 0.1, 0.1, 0.05]
const REGIONS = ['US West', 'US East', 'UK', 'Germany', 'India', 'Singapore', 'Brazil', 'Canada', 'Australia', 'Nigeria']

const FIRST = ['Aisha', 'Ben', 'Carla', 'Dev', 'Elena', 'Farid', 'Grace', 'Hiro', 'Ines', 'Jonas', 'Kavya', 'Liam', 'Maya', 'Nikolai', 'Olu', 'Priya', 'Quinn', 'Rosa', 'Sam', 'Tariq', 'Uma', 'Victor', 'Wen', 'Xavier', 'Yara', 'Zoe', 'Arjun', 'Beatriz', 'Chen', 'Dana', 'Emeka', 'Freya', 'Gabriel', 'Hana', 'Ivan', 'Jade']
const LAST = ['Okafor', 'Müller', 'Sato', 'Rodriguez', 'Patel', 'Nguyen', 'Kowalski', 'Haddad', 'Silva', 'Andersen', 'Ivanova', 'Mensah', 'Rossi', 'Khan', 'Oyelaran', 'Whitfield', 'Alvarez', 'Hoffmann', 'Kim', 'Raman', 'Dubois', 'Tanaka', 'Novak', 'Baptiste']

function pick<T>(rng: () => number, arr: T[], weights?: number[]): T {
  if (!weights) return arr[Math.floor(rng() * arr.length)]
  const r = rng(); let acc = 0
  for (let i = 0; i < arr.length; i++) { acc += weights[i]; if (r < acc) return arr[i] }
  return arr[arr.length - 1]
}

export function generatePersonas(n: number, seed = 42): Persona[] {
  const rng = mulberry32(seed)
  const out: Persona[] = []
  for (let i = 0; i < n; i++) {
    // Stratify profession groups roughly evenly, with a bit of noise.
    const group = PROFESSION_GROUPS[(i + Math.floor(rng() * 2)) % PROFESSION_GROUPS.length]
    const tech = pick(rng, TECH, TECH_W)
    const income = pick(rng, INCOME, INCOME_W)
    const econ: EconomicStance =
      income === 'High' ? pick(rng, ECON, [0.1, 0.4, 0.5]) :
      income === 'Low' ? pick(rng, ECON, [0.6, 0.35, 0.05]) : pick(rng, ECON, [0.3, 0.5, 0.2])
    // Heavy-tailed influence: most people are quiet, a few are loud.
    const influence = Math.min(1, Math.pow(rng(), 3) * 1.6 + rng() * 0.08)
    out.push({
      id: i,
      name: `${pick(rng, FIRST)} ${pick(rng, LAST)}`,
      profession: pick(rng, PROFESSIONS[group]),
      professionGroup: group,
      ageBand: group === 'Students' ? pick(rng, AGES, [0.7, 0.25, 0.05, 0, 0]) : pick(rng, AGES, AGE_W),
      income: group === 'Students' ? pick(rng, INCOME, [0.6, 0.3, 0.1, 0, 0]) : income,
      ideology: pick(rng, IDEOLOGIES, [0.3, 0.35, 0.25, 0.1]),
      economic: econ,
      tech,
      region: pick(rng, REGIONS),
      role: pick(rng, ROLES, ROLE_W),
      traits: {
        openness: rng(), conscientiousness: rng(), extraversion: rng(),
        agreeableness: rng(), neuroticism: rng(),
      },
      influence,
      activity: 0.2 + rng() * 0.8,
    })
  }
  return out
}

export const GROUP_COLORS: Record<ProfessionGroup, number> = {
  Engineering: 0x7c9cff,
  Design: 0xd58cff,
  Marketing: 0xff8fb1,
  Finance: 0x5ad1c5,
  Operations: 0xa7b4cc,
  Healthcare: 0x6fe3a5,
  Education: 0xf5c242,
  'Retail & Service': 0xff9f5a,
  Students: 0x8fd3ff,
  Executives: 0xffd166,
}

export function hexToCss(n: number) { return '#' + n.toString(16).padStart(6, '0') }

export const INTENT_COLOR: Record<Intent, string> = { 'Would buy/use': '#3ddc97', Maybe: '#f5c242', 'Would not': '#ff6b6b' }
