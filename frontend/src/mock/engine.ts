import type {
  Persona, Stimulus, StimulusType, Verdict, SimEvent, Scorecard, DimensionScore, SegmentScore,
  Objection, MissingKpi, Variant, MarketBrief, Intent, ChangedMind, InterviewSummary,
} from '../types'

type MockInterview = { intent: Intent; recommend: number; changedMind: ChangedMind; quote: string; better: 'Better' | 'About the same' | 'Worse' | "Don't know any"; alt: string; fix: string }
import { mulberry32, PROFESSION_GROUPS } from './personas'

/**
 * Mock simulation engine. Produces the same event stream the real backend will,
 * but computes opinions from persona attributes instead of calling an LLM.
 * It is intentionally opinionated so the UI shows realistic dynamics:
 * price-sensitive segments object to price, laggards object to complexity, etc.
 */

export interface EngineOptions {
  stimulus: Stimulus
  personas: Persona[]
  rounds: number
  /** Wall-clock ms per social round. */
  msPerRound: number
  seed?: number
  /** Emit a simulated market scan before first impressions. */
  marketScan?: boolean
  onEvent: (e: SimEvent) => void
}

const PRODUCT_MARKET: MarketBrief = {
  category: 'Consumer gadgets in this category (simulated)',
  summary: 'Simulated market: a well-known leader, a cheap marketplace option, a premium design rival and a DIY workaround already cover most of the need. Not real market data.',
  priceRange: '$12 DIY, $25-99 mainstream, $200+ premium',
  competitors: [
    { name: 'Category leader', maker: 'Big brand', price: '$99', pitch: 'The one most people have heard of', likedFor: 'reliable, lots of reviews', complaints: 'pricey, the app wants an account', url: '' },
    { name: 'Budget pick', maker: 'Marketplace brand', price: '$25', pitch: 'Does the basics for a quarter of the price', likedFor: 'cheap and good enough', complaints: 'flimsy, uneven quality', url: '' },
    { name: 'Premium rival', maker: 'Design brand', price: '$220', pitch: 'Beautiful object, premium materials', likedFor: 'looks great on a desk', complaints: 'overpriced for what it does', url: '' },
    { name: 'Timer plug hack', maker: 'Generic', price: '$12', pitch: 'A smart plug on a schedule does the main trick', likedFor: 'costs almost nothing', complaints: 'fiddly setup, no colour control', url: '' },
  ],
  news: [
    { headline: 'Shoppers trade down as gadget prices rise', source: 'Simulated Daily', date: '2026', gist: 'Mid-priced devices lose share to cheap marketplace brands.', url: '', tone: 'negative' },
    { headline: 'Reviewers warm to a new wave of well-designed home devices', source: 'Simulated Tech', date: '2026', gist: 'Design-led products get strong reviews and social buzz.', url: '', tone: 'positive' },
    { headline: 'Regulators look at subscription traps in connected devices', source: 'Simulated Times', date: '2026', gist: 'Apps that lock features behind subscriptions draw complaints.', url: '', tone: 'negative' },
  ],
  buyerComplaints: ['apps that need an account', 'short lifespan', 'prices that hide subscriptions'],
  substitutes: ['a smart plug on a timer', 'doing nothing and living with it'],
  sources: [],
}
const IDEA_MARKET: MarketBrief = {
  category: 'Software and services for this need (simulated)',
  summary: 'Simulated market: an incumbent platform, agencies, a DIY spreadsheet-and-survey routine and a funded startup already compete for the same budget. Not real market data.',
  priceRange: '$0 DIY, $50-300/month tools, $5k+ agency projects',
  competitors: [
    { name: 'Incumbent platform', maker: 'Large vendor', price: '$300/month', pitch: 'The default enterprise choice', likedFor: 'trusted, integrates with everything', complaints: 'expensive, slow to set up', url: '' },
    { name: 'Agency or consultants', maker: 'Various', price: '$5,000+ per project', pitch: 'Humans do it for you', likedFor: 'real expertise', complaints: 'slow and costly', url: '' },
    { name: 'Spreadsheet + survey tool', maker: 'DIY', price: '$0-30/month', pitch: 'What most small teams do today', likedFor: 'cheap and flexible', complaints: 'manual, error-prone', url: '' },
    { name: 'Well-funded startup', maker: 'VC-backed', price: '$99/month', pitch: 'Modern, AI-first take on the problem', likedFor: 'slick product', complaints: 'unproven, may pivot', url: '' },
  ],
  news: [
    { headline: 'Budgets tighten for new software tools', source: 'Simulated Business', date: '2026', gist: 'Teams consolidate tools and cut experiments.', url: '', tone: 'negative' },
    { headline: 'AI tools win over small teams', source: 'Simulated Tech', date: '2026', gist: 'Adoption of AI-first tools keeps rising among startups.', url: '', tone: 'positive' },
  ],
  buyerComplaints: ['hard to prove ROI', 'another tool to learn', 'pricing that scales too fast'],
  substitutes: ['doing it by hand', 'asking a few customers directly'],
  sources: [],
}
export const MOCK_MARKET: Record<StimulusType, MarketBrief> = { creative: PRODUCT_MARKET, website: PRODUCT_MARKET, offer: PRODUCT_MARKET, idea: IDEA_MARKET }

type Bank = { objections: string[]; missing: string[]; praise: string[]; kpis: MissingKpi[]; variants: Variant[]; dims: { name: string; weight: number }[] }

const BANKS: Record<StimulusType, Bank> = {
  creative: {
    objections: [
      'The headline doesn\'t say what the product does',
      'Price is nowhere on the creative, feels like it\'s hiding something',
      'Looks like every other premium gadget ad',
      'The tagline is clever but I had to read it twice',
      'Can\'t tell who this is for',
      'Too dark, the product is barely visible',
      'No proof: no review, no number, no comparison',
      'The CTA is weak, "learn more" doesn\'t make me do anything',
    ],
    missing: ['a price', 'a concrete benefit in numbers', 'social proof', 'a clear CTA', 'the product name in large type', 'a comparison to what I use today'],
    praise: ['The mood is beautiful', 'Tagline is memorable', 'Clean, premium feel', 'I get the vibe instantly', 'Nice restraint, not shouty'],
    kpis: [
      { kpi: 'Click-through rate by segment', why: 'The creative lands differently by audience; a single CTR hides that.', target: '> 1.2% on developers, > 0.6% general' },
      { kpi: '5-second comprehension', why: 'Agents repeatedly misread what the product is.', target: '> 70% correct recall in a 5-second test' },
      { kpi: 'Brand recall vs tagline recall', why: 'Tagline is memorable but product name isn\'t.', target: 'Unaided recall > 30%' },
      { kpi: 'Cost per qualified click', why: 'Broad reach is cheap; the right clicks aren\'t.', target: '< $2.50' },
    ],
    variants: [
      { label: 'Add the price and a 2-line benefit under the tagline', change: 'Clarity up, mystery down', predictedDelta: +0.8 },
      { label: 'Lighter scene with product centered', change: 'Product visibility', predictedDelta: +0.4 },
      { label: 'Swap tagline for a plain-language promise', change: 'Loses charm, gains comprehension', predictedDelta: +0.2 },
    ],
    dims: [
      { name: 'Clarity', weight: 0.25 }, { name: 'Desirability', weight: 0.25 }, { name: 'Credibility', weight: 0.15 },
      { name: 'Differentiation', weight: 0.15 }, { name: 'Shareability', weight: 0.1 }, { name: 'Price-value fit', weight: 0.1 },
    ],
  },
  website: {
    objections: [
      'I scrolled twice and still don\'t know the price',
      'Hero copy is all adjectives, no specifics',
      'No reviews or logos, so why would I trust it',
      'The signup form asks for too much up front',
      'Looks fine on desktop, the mobile menu is a mess',
      'Loads slow and the first thing I see is a cookie wall',
      'Pricing page compares to nothing, so I can\'t judge value',
      'Where is the "how it works"?',
    ],
    missing: ['pricing above the fold', 'customer logos or reviews', 'a product screenshot', 'a comparison table', 'a free trial', 'a security/privacy note'],
    praise: ['Fast and clean', 'The demo video sold it', 'Pricing is honest', 'Good FAQ', 'Nice to see real screenshots'],
    kpis: [
      { kpi: 'Scroll depth to pricing', why: 'Most agents gave up before finding the price.', target: '> 60% reach pricing' },
      { kpi: 'Hero-to-signup conversion', why: 'The hero promises, the form blocks.', target: '> 3% visitors' },
      { kpi: 'Trust signal exposure', why: 'Trust objections dominate without logos/reviews.', target: 'Logos visible in first viewport' },
      { kpi: 'Mobile bounce rate', why: 'Mobile users reacted far worse than desktop.', target: '< 45%' },
    ],
    variants: [
      { label: 'Put price and a 3-tier table in the first scroll', change: 'Removes the biggest objection', predictedDelta: +1.1 },
      { label: 'Replace adjectives with one measurable claim', change: 'Credibility', predictedDelta: +0.6 },
      { label: 'Cut signup form to email only', change: 'Conversion', predictedDelta: +0.5 },
    ],
    dims: [
      { name: 'Clarity', weight: 0.2 }, { name: 'Credibility', weight: 0.25 }, { name: 'Desirability', weight: 0.2 },
      { name: 'Price-value fit', weight: 0.15 }, { name: 'Usability', weight: 0.2 },
    ],
  },
  offer: {
    objections: [
      'The discount is big enough to make me think the full price is fake',
      '"Ends Sunday" every week, I\'ve seen this trick',
      'Terms say auto-renew, that\'s the real price',
      'A percentage off means nothing without the base price',
      'It\'s a bundle of things I don\'t need to get the one I do',
      'Why first 500 only? Feels manufactured',
      'Nice price but I don\'t trust the brand yet',
      'No money-back guarantee, so no',
    ],
    missing: ['the base price', 'a guarantee', 'what happens after the promo', 'a single-item option', 'a real deadline', 'what "limited" actually means'],
    praise: ['Good value, I\'d try it', 'Clear and simple', 'The bundle makes sense', 'Early-bird feels fair', 'Love a transparent price'],
    kpis: [
      { kpi: 'Offer conversion by income band', why: 'Frugal and premium segments reacted in opposite directions.', target: 'Track separately' },
      { kpi: 'Refund/chargeback rate', why: 'Auto-renew terms triggered distrust; refunds will follow.', target: '< 3%' },
      { kpi: 'Discount elasticity', why: 'Agents doubted the anchor price; test 10/20/30% off.', target: 'Find the knee' },
      { kpi: 'Urgency lift vs no-deadline control', why: 'Urgency was read as a trick by a large segment.', target: 'Lift > 15% or drop it' },
    ],
    variants: [
      { label: 'Show base price, promo price, and post-promo price side by side', change: 'Kills the "fake anchor" objection', predictedDelta: +0.9 },
      { label: 'Add a 30-day money-back guarantee', change: 'Trust', predictedDelta: +0.7 },
      { label: 'Drop "first 500" scarcity, keep the date', change: 'Fewer "manufactured" comments', predictedDelta: +0.3 },
    ],
    dims: [
      { name: 'Price-value fit', weight: 0.3 }, { name: 'Credibility', weight: 0.25 }, { name: 'Clarity', weight: 0.15 },
      { name: 'Urgency fit', weight: 0.15 }, { name: 'Desirability', weight: 0.15 },
    ],
  },
  idea: {
    objections: [
      'Who pays, and how much? The model is hand-wavy',
      'Big players can copy this in a quarter',
      'The problem is real but small',
      'Acquisition cost will eat the margin',
      'Regulation is the actual moat here and you don\'t mention it',
      'This is a feature, not a company',
      'The target user doesn\'t buy software, their boss does',
      'Nice idea, but why hasn\'t anyone done it? Usually there\'s a reason',
    ],
    missing: ['a pricing model', 'unit economics', 'a wedge customer', 'a go-to-market channel', 'a defensibility story', 'evidence the problem is painful'],
    praise: ['Clear problem, I\'ve felt it', 'The wedge is smart', 'Timing looks right', 'Simple enough to explain in a sentence', 'I\'d pay for this'],
    kpis: [
      { kpi: 'CAC payback period', why: 'Nobody could tell if acquisition is affordable.', target: '< 12 months' },
      { kpi: 'Activation rate', why: 'The idea depends on users reaching the "aha" quickly.', target: '> 40% in first session' },
      { kpi: 'Net revenue retention', why: 'Expansion is implied but not measured.', target: '> 100%' },
      { kpi: 'Gross margin at scale', why: 'If it\'s LLM-heavy, margin is the whole question.', target: '> 65%' },
      { kpi: 'Time-to-value', why: 'Gatekeepers asked how long until it pays off.', target: '< 1 week' },
    ],
    variants: [
      { label: 'Name one wedge customer and their current spend', change: 'Makes the market concrete', predictedDelta: +1.0 },
      { label: 'Add a one-line pricing model with a margin estimate', change: 'Viability', predictedDelta: +0.8 },
      { label: 'Lead with the moat (data, distribution, or regulation)', change: 'Defensibility', predictedDelta: +0.5 },
    ],
    dims: [
      { name: 'Problem clarity', weight: 0.15 }, { name: 'Desirability', weight: 0.2 }, { name: 'Viability', weight: 0.25 },
      { name: 'Feasibility', weight: 0.15 }, { name: 'Differentiation', weight: 0.15 }, { name: 'Risk', weight: 0.1 },
    ],
  },
}

const EXPERTS = [
  { name: 'Mira Chen', role: 'CFO' }, { name: 'Tomas Reyes', role: 'Growth marketer' }, { name: 'Lena Hoffmann', role: 'UX research lead' },
  { name: 'Kwame Asante', role: 'Product counsel' }, { name: 'Sofia Bianchi', role: 'Data scientist' }, { name: 'Raj Mehta', role: 'Supply chain' },
]

type TechAdoption = Persona['tech']

function techScore(t: TechAdoption) {
  return { Innovator: 0.9, 'Early adopter': 0.75, 'Early majority': 0.55, 'Late majority': 0.4, Laggard: 0.25 }[t]
}
function priceSensitivity(p: Persona) {
  const inc = { Low: 0.9, 'Lower-middle': 0.75, Middle: 0.55, 'Upper-middle': 0.35, High: 0.2 }[p.income]
  const econ = { Frugal: 0.9, 'Value-seeking': 0.55, Premium: 0.2 }[p.economic]
  return (inc + econ) / 2
}

/** Base propensity of a persona toward this stimulus, 0..1. */
function baseAffinity(p: Persona, s: Stimulus, rng: () => number) {
  const brief = s.brief.toLowerCase()
  const mentionsPrice = /\$\d|price|₹|€|£|\d+ ?(usd|dollars)/.test(brief)
  const premiumCue = /premium|smart|ai|luxury|pro\b/.test(brief)
  const concreteCue = /\d+%|\d+ (minutes|hours|days)|guarantee|free trial|reviews?/.test(brief)

  // Centre around "mildly positive"; penalties pull price-sensitive and sceptical segments down.
  let a = 0.6
  a += (techScore(p.tech) - 0.5) * 0.45
  a += (p.traits.openness - 0.5) * 0.25
  if (premiumCue) a -= (priceSensitivity(p) - 0.4) * 0.3
  if (mentionsPrice) a -= (priceSensitivity(p) - 0.5) * 0.2
  if (concreteCue) a += 0.1 * (1 - p.traits.openness) + 0.04
  if (s.type === 'idea') {
    if (p.professionGroup === 'Finance' || p.role === 'Investor' || p.role === 'Gatekeeper') a -= 0.1
    if (p.professionGroup === 'Executives') a += 0.05
  }
  if (s.type === 'creative' && p.professionGroup === 'Design') a -= 0.08 // designers are harsh on creatives
  if (s.type === 'website' && p.professionGroup === 'Engineering') a -= 0.05
  if (s.type === 'offer') a -= (priceSensitivity(p) - 0.5) * 0.25 // frugal people like offers more, premium less
  a += (rng() - 0.5) * 0.36
  return Math.max(0.03, Math.min(0.97, a))
}

function pickObjection(p: Persona, bank: Bank, rng: () => number) {
  const ps = priceSensitivity(p)
  const idx = Math.floor(rng() * bank.objections.length)
  // Bias price-sensitive personas toward price objections (index 1 in each bank is price-ish).
  if (ps > 0.65 && rng() < 0.5) return bank.objections[1]
  if (p.tech === 'Laggard' && rng() < 0.4) return bank.objections[bank.objections.length - 1]
  return bank.objections[idx]
}

function intentFor(score: number): Verdict['intent'] {
  return score >= 6.5 ? 'Would buy/use' : score >= 4 ? 'Maybe' : 'Would not'
}

export function runMockSimulation(opts: EngineOptions): { stop: () => void } {
  const { stimulus, personas, rounds, msPerRound, onEvent } = opts
  const rng = mulberry32(opts.seed ?? 7)
  const bank = BANKS[stimulus.type]
  let stopped = false
  const timers: number[] = []
  const later = (ms: number, fn: () => void) => { const id = window.setTimeout(() => { if (!stopped) fn() }, ms); timers.push(id) }
  const now = () => performance.now()

  const scores = new Map<number, number>()
  const initialScores = new Map<number, number>()
  const verdicts = new Map<number, Verdict>()
  const posts: { id: number; agentId: number; score: number; round: number }[] = []
  let postId = 0

  // ---- Stage 0: market scan (simulated) ----
  const t0 = opts.marketScan === false ? 0 : 1400
  if (t0) {
    onEvent({ kind: 'stage', stage: 'market', t: now() })
    later(t0 - 200, () => onEvent({ kind: 'market', status: 'simulated', brief: MOCK_MARKET[stimulus.type], t: now() }))
  } else {
    onEvent({ kind: 'market', status: 'off', t: now() })
  }

  // ---- Stage 1: impressions (burst, fast) ----
  later(t0, () => onEvent({ kind: 'stage', stage: 'impressions', t: now() }))
  const impressionMs = Math.min(4000, 400 + personas.length * 2.2)
  personas.forEach((p, i) => {
    later(t0 + (i / personas.length) * impressionMs, () => {
      const a = baseAffinity(p, stimulus, rng)
      const score = Math.round(a * 100) / 10
      scores.set(p.id, score); initialScores.set(p.id, score)
      const objection = pickObjection(p, bank, rng)
      const v: Verdict = {
        agentId: p.id, score, intent: intentFor(score),
        objection,
        missing: bank.missing[Math.floor(rng() * bank.missing.length)],
        reaction: score >= 6.5 ? bank.praise[Math.floor(rng() * bank.praise.length)] : objection,
      }
      verdicts.set(p.id, v)
      onEvent({ kind: 'impression', agentId: p.id, score, t: now() })
    })
  })

  // ---- Stage 2: social rounds ----
  const socialStart = t0 + impressionMs + 600
  later(socialStart, () => onEvent({ kind: 'stage', stage: 'social', t: now() }))
  const byInfluence = [...personas].sort((a, b) => b.influence - a.influence)
  const opened = new Set<number>()  // everyone opens the app at least once over the rounds
  for (let r = 1; r <= rounds; r++) {
    const roundStart = socialStart + (r - 1) * msPerRound
    later(roundStart, () => onEvent({ kind: 'round', round: r, totalRounds: rounds, t: now() }))
    const activeCount = Math.max(12, Math.round(personas.length * (0.11 + rng() * 0.06)))
    const active: Persona[] = []
    for (let k = 0; k < activeCount; k++) {
      // Who acts: influence-weighted with a long tail of ordinary people.
      active.push(rng() < 0.35 ? byInfluence[Math.floor(rng() * Math.min(byInfluence.length, 60))] : personas[Math.floor(rng() * personas.length)])
    }
    active.forEach(p => opened.add(p.id))
    const waiting = personas.filter(p => !opened.has(p.id))
    for (let i = waiting.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [waiting[i], waiting[j]] = [waiting[j], waiting[i]] }
    const lurkers = waiting.slice(0, Math.ceil(waiting.length / (rounds - r + 1)))
    lurkers.forEach(p => opened.add(p.id))
    active.forEach((p, k) => {
      const at = roundStart + 150 + (k / activeCount) * (msPerRound - 400)
      later(at, () => {
        const v = verdicts.get(p.id); if (!v) return
        const s = scores.get(p.id) ?? v.score
        const roll = rng()
        if (posts.length > 3 && roll < 0.45) {
          // reply to an existing post, preferring recent + influential authors
          const pool = posts.slice(-Math.min(posts.length, 40))
          const target = pool[Math.floor(Math.pow(rng(), 0.6) * pool.length)]
          if (target.agentId === p.id) return
          const agree = Math.abs(target.score - s) < 2.5
          const text = agree
            ? (s >= 6 ? `Agree with ${personas[target.agentId].name.split(' ')[0]}: ${v.reaction.toLowerCase()}.` : `Same here. ${v.objection}.`)
            : (s >= 6 ? `Not my experience. ${v.reaction}.` : `Disagree. ${v.objection}.`)
          const id = ++postId
          posts.push({ id, agentId: p.id, score: s, round: r })
          onEvent({ kind: 'reply', id, agentId: p.id, toAgentId: target.agentId, toPostId: target.id, text, score: s, round: r, t: now() })
          // persuasion: the target's author and a few readers drift toward the replier if they're influential
          persuade(target.agentId, p, s, r, 1, id)
        } else if (posts.length > 0 && roll < 0.55) {
          const target = posts[Math.floor(Math.pow(rng(), 0.4) * posts.length)]
          if (target.agentId === p.id) return
          onEvent({ kind: 'repost', agentId: p.id, fromAgentId: target.agentId, postId: target.id, round: r, t: now() })
          persuade(p.id, personas[target.agentId], target.score, r, 1, target.id)
        } else if (posts.length > 0 && roll < 0.72) {
          like(p, s, r)
        } else {
          const id = ++postId
          posts.push({ id, agentId: p.id, score: s, round: r })
          const text = s >= 6.5 ? `${v.reaction}. Would ${stimulus.type === 'idea' ? 'back' : 'buy'} it.` : s >= 4 ? `${v.reaction}. On the fence; missing ${v.missing}.` : `${v.objection}. Pass.`
          onEvent({ kind: 'post', id, agentId: p.id, text, score: s, round: r, t: now() })
        }
        // ambient exposure: the feed shows this to a handful of readers, who drift slightly toward loud voices.
        const readers = 3 + Math.round(p.influence * 9)
        const shownId = posts.length ? posts[posts.length - 1].id : undefined
        for (let j = 0; j < readers; j++) {
          const reader = personas[Math.floor(rng() * personas.length)]
          if (reader.id === p.id) continue
          onEvent({ kind: 'exposure', agentId: reader.id, fromAgentId: p.id, round: r, t: now() })
          persuade(reader.id, p, s, r, 0.35, shownId)
        }
      })
    })
    // People who hadn't opened the app yet mostly scroll and like.
    lurkers.forEach((p, k) => {
      later(roundStart + 200 + (k / Math.max(1, lurkers.length)) * (msPerRound - 400), () => {
        const s = scores.get(p.id); if (s == null || !posts.length) return
        if (rng() < 0.6) like(p, s, r)
      })
    })
  }

  function like(p: Persona, s: number, round: number) {
    const pool = posts.slice(-Math.min(posts.length, 60)).filter(x => x.agentId !== p.id && Math.abs(x.score - s) < 2.5)
    if (!pool.length) return
    const target = pool[Math.floor(rng() * pool.length)]
    onEvent({ kind: 'like', agentId: p.id, fromAgentId: target.agentId, postId: target.id, round, t: now() })
  }

  function persuade(targetId: number, by: Persona, towards: number, round: number, strength = 1, postId?: number) {
    const cur = scores.get(targetId); if (cur == null) return
    const target = personas[targetId]
    // Loud voices move people; agreeable, less conscientious readers move more.
    const pull = Math.sqrt(by.influence) * (0.4 + target.traits.agreeableness * 0.6) * (1 - target.traits.conscientiousness * 0.3) * strength
    const next = Math.round((cur + (towards - cur) * pull * 0.45) * 10) / 10
    if (Math.abs(next - cur) >= 0.5) {
      scores.set(targetId, next)
      onEvent({ kind: 'mind_change', agentId: targetId, from: cur, to: next, causedBy: by.id, postId, round, t: now() })
    } else {
      scores.set(targetId, next)
    }
  }

  // ---- Stage 2b: exit interviews. Stated intent is more conservative than the score, as in real panels. ----
  const interviews = new Map<number, MockInterview>()
  const interviewsStart = socialStart + rounds * msPerRound + 300
  const interviewMs = Math.min(3000, 300 + personas.length * 1.5)
  const alts = MOCK_MARKET[stimulus.type].competitors.map(c => c.name)
  later(interviewsStart, () => onEvent({ kind: 'stage', stage: 'interviews', t: now() }))
  personas.forEach((p, i) => {
    later(interviewsStart + 100 + (i / personas.length) * interviewMs, () => {
      const v = verdicts.get(p.id); if (!v) return
      const s = scores.get(p.id) ?? v.score, d = s - (initialScores.get(p.id) ?? s)
      const intent: Intent = (s >= 7.5 && rng() < 0.5) || (s >= 6.5 && rng() < 0.15) ? 'Would buy/use' : s >= 4.5 ? 'Maybe' : 'Would not'
      const knowsAlts = techScore(p.tech) >= 0.55 || rng() < 0.4
      const iv: MockInterview = {
        intent, recommend: Math.round(Math.max(0, Math.min(10, s + (rng() - 0.5) * 2))),
        changedMind: Math.abs(d) < 0.5 ? 'No' : d > 0 ? 'More positive' : 'More negative',
        quote: s >= 6.5 ? `${v.reaction}. I'd ${intent === 'Would buy/use' ? 'get one' : 'think about it'}.` : `${v.objection}.`,
        better: !knowsAlts ? "Don't know any" : s >= 7 ? 'Better' : s >= 5 ? 'About the same' : 'Worse',
        alt: knowsAlts ? alts[Math.floor(rng() * alts.length)] : 'nothing',
        fix: v.missing,
      }
      interviews.set(p.id, iv)
      onEvent({ kind: 'interview', agentId: p.id, intent: iv.intent, recommend: iv.recommend, changedMind: iv.changedMind, quote: iv.quote, t: now() })
    })
  })

  // ---- Stage 3: experts ----
  const expertsStart = interviewsStart + interviewMs + 500
  later(expertsStart, () => onEvent({ kind: 'stage', stage: 'experts', t: now() }))
  bank.kpis.forEach((k, i) => {
    const ex = EXPERTS[i % EXPERTS.length]
    later(expertsStart + 300 + i * 700, () => onEvent({ kind: 'expert', name: ex.name, role: ex.role, finding: `Missing KPI: ${k.kpi}. ${k.why}`, t: now() }))
  })

  // ---- Stage 4: judge ----
  const judgeStart = expertsStart + 300 + bank.kpis.length * 700 + 400
  later(judgeStart, () => onEvent({ kind: 'stage', stage: 'judge', t: now() }))
  later(judgeStart + 1800, () => {
    onEvent({ kind: 'stage', stage: 'done', t: now() })
    onEvent({ kind: 'done', t: now() })
  })

  // Expose a scorecard builder on the returned handle via closure (store calls buildScorecard after 'done').
  ;(runMockSimulation as unknown as { last?: () => Scorecard }).last = () => buildScorecard(stimulus, personas, verdicts, scores, initialScores, bank, interviews)

  return { stop: () => { stopped = true; timers.forEach(clearTimeout) } }
}

export function getLastScorecard(): Scorecard | null {
  const fn = (runMockSimulation as unknown as { last?: () => Scorecard }).last
  return fn ? fn() : null
}

function summarizeInterviews(personas: Persona[], interviews: Map<number, MockInterview>): InterviewSummary | null {
  const rows = personas.filter(p => interviews.has(p.id)).map(p => ({ p, iv: interviews.get(p.id)! }))
  const n = rows.length
  if (!n) return null
  const pct = (c: number) => Math.round((c / n) * 100)
  const count = <T,>(f: (r: typeof rows[number]) => T) => { const m = new Map<T, number>(); rows.forEach(r => m.set(f(r), (m.get(f(r)) ?? 0) + 1)); return m }
  const prom = rows.filter(r => r.iv.recommend >= 9).length, det = rows.filter(r => r.iv.recommend <= 6).length
  const ch = count(r => r.iv.changedMind), vs = count(r => r.iv.better)
  const who = (p: Persona) => `${p.name}, ${p.profession}, ${p.region}`
  const top = (m: Map<string, number>, k: number) => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, k)
  const altCounts = count(r => r.iv.alt); altCounts.delete('nothing')
  const fixCounts = new Map<string, number>(); rows.filter(r => r.iv.intent !== 'Would buy/use').forEach(r => fixCounts.set(r.iv.fix, (fixCounts.get(r.iv.fix) ?? 0) + 1))
  const themeCounts = count(r => r.iv.quote)
  return {
    n, nps: Math.round(((prom - det) / n) * 100), promoters: pct(prom), passives: pct(n - prom - det), detractors: pct(det),
    changedMind: { no: pct(ch.get('No') ?? 0), positive: pct(ch.get('More positive') ?? 0), negative: pct(ch.get('More negative') ?? 0) },
    vsAlternatives: { better: pct(vs.get('Better') ?? 0), same: pct(vs.get('About the same') ?? 0), worse: pct(vs.get('Worse') ?? 0), unknown: pct(vs.get("Don't know any") ?? 0) },
    alternatives: top(altCounts, 6).map(([name, c]) => ({ name, count: c })),
    themes: top(themeCounts, 4).map(([text, c]) => ({ text, count: c, quotes: rows.filter(r => r.iv.quote === text).slice(0, 2).map(r => ({ agent: who(r.p), text })) })),
    fixes: top(fixCounts, 5).map(([text, c]) => ({ text, count: c })),
    quotes: (['Would buy/use', 'Maybe', 'Would not'] as Intent[]).flatMap(i => rows.filter(r => r.iv.intent === i).sort((a, b) => b.p.influence - a.p.influence).slice(0, 3).map(r => ({ agent: who(r.p), intent: i, text: r.iv.quote }))),
  }
}

function buildScorecard(
  stimulus: Stimulus, personas: Persona[], verdicts: Map<number, Verdict>,
  scores: Map<number, number>, initial: Map<number, number>, bank: Bank, interviews: Map<number, MockInterview>,
): Scorecard {
  const n = personas.length
  const finalScores = personas.map(p => scores.get(p.id) ?? 5)
  const mean = finalScores.reduce((a, b) => a + b, 0) / n
  const initMean = personas.map(p => initial.get(p.id) ?? 5).reduce((a, b) => a + b, 0) / n
  const sd = Math.sqrt(finalScores.reduce((a, b) => a + (b - mean) ** 2, 0) / n)
  const rng = mulberry32(99)

  const dimensions: DimensionScore[] = bank.dims.map(d => {
    const jitter = (rng() - 0.5) * 2.2
    const s = Math.max(1, Math.min(9.8, mean + jitter))
    return { name: d.name, weight: d.weight, score: Math.round(s * 10) / 10, note: s < 5 ? 'Below the bar' : s < 7 ? 'Acceptable' : 'Strong' }
  })
  const overall = Math.round(dimensions.reduce((a, d) => a + d.score * d.weight, 0) * 10) / 10

  // Intent is what they said in the exit interview; score cut-offs only if the run stopped before interviews.
  const intentOf = (p: Persona): Intent => interviews.get(p.id)?.intent ?? intentFor(scores.get(p.id) ?? 5)
  const seg = (group: string, key: (p: Persona) => string): SegmentScore[] => {
    const m = new Map<string, { sum: number; n: number; buy: number }>()
    personas.forEach(p => {
      const k = key(p); const s = scores.get(p.id) ?? 5
      const cur = m.get(k) ?? { sum: 0, n: 0, buy: 0 }
      cur.sum += s; cur.n++; if (intentOf(p) === 'Would buy/use') cur.buy++
      m.set(k, cur)
    })
    return [...m.entries()].map(([segment, v]) => ({ segment, group, score: Math.round((v.sum / v.n) * 10) / 10, n: v.n, intent: Math.round((v.buy / v.n) * 100) }))
      .sort((a, b) => b.score - a.score)
  }
  const segments = [
    ...seg('Profession', p => p.professionGroup),
    ...seg('Ideology', p => p.ideology),
    ...seg('Income', p => p.income),
    ...seg('Age', p => p.ageBand),
    ...seg('Tech adoption', p => p.tech),
    ...seg('Role', p => p.role),
  ]

  const objMap = new Map<string, Objection>()
  personas.forEach(p => {
    const v = verdicts.get(p.id); if (!v) return
    if ((scores.get(p.id) ?? 5) >= 6.5) return
    const o = objMap.get(v.objection) ?? { text: v.objection, count: 0, influence: 0, quotes: [] }
    o.count++; o.influence += p.influence
    if (o.quotes.length < 3 && p.influence > 0.3) o.quotes.push({ agent: `${p.name}, ${p.profession}`, text: v.reaction })
    objMap.set(v.objection, o)
  })
  const objections = [...objMap.values()].sort((a, b) => (b.count * (1 + b.influence)) - (a.count * (1 + a.influence))).slice(0, 6)

  const missCount = new Map<string, number>()
  personas.forEach(p => { const v = verdicts.get(p.id); if (v) missCount.set(v.missing, (missCount.get(v.missing) ?? 0) + 1) })
  const missing = [...missCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([m]) => m)

  const stated = personas.map(intentOf)
  const buy = stated.filter(i => i === 'Would buy/use').length, no = stated.filter(i => i === 'Would not').length
  const agreement = Math.round(Math.max(0, 1 - sd / 3.2) * 100)
  const verdict = overall >= 7 ? 'Strong: ship it, fix the gaps' : overall >= 5.5 ? 'Promising but not there yet' : overall >= 4 ? 'Weak: rework before spending on it' : 'Do not proceed as is'

  const variants: Variant[] = bank.variants.map(v => ({ ...v, predictedDelta: Math.round((v.predictedDelta + (rng() - 0.5) * 0.3) * 10) / 10 }))
  const kpis: MissingKpi[] = bank.kpis

  return {
    overall, verdict,
    summary: `${n} simulated people from ${PROFESSION_GROUPS.length} profession groups reviewed "${stimulus.title}". ` +
      `${Math.round((buy / n) * 100)}% would ${stimulus.type === 'idea' ? 'back' : 'buy'} it, ${Math.round((no / n) * 100)}% would not. ` +
      `Opinion ${mean - initMean >= 0 ? 'improved' : 'worsened'} by ${Math.abs(mean - initMean).toFixed(1)} points during discussion. ` +
      `Top objection: "${objections[0]?.text ?? 'none'}".`,
    dimensions, segments, objections, missing, missingKpis: kpis, variants,
    polarization: Math.round(sd * 100) / 100,
    shift: Math.round((mean - initMean) * 100) / 100,
    confidence: {
      sample: n, agreement,
      label: n >= 1000 ? 'High' : n >= 300 ? 'Medium' : 'Low',
      note: `${n} agents, ${agreement}% agreement. Mock engine: opinions derived from persona attributes, not an LLM.`,
    },
    intentSplit: { buy: Math.round((buy / n) * 100), maybe: Math.round(((n - buy - no) / n) * 100), no: Math.round((no / n) * 100) },
    intentSource: interviews.size ? 'exit interviews' : 'score cut-offs',
    interviews: summarizeInterviews(personas, interviews),
    marketPosition: `Simulated: the crowd compared it with ${MOCK_MARKET[stimulus.type].competitors[0].name.toLowerCase()} and cheaper workarounds; mock engine, not a real market read.`,
  }
}
