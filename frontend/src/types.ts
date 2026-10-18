// Shared domain types. The backend will emit exactly these shapes over WebSocket,
// so the mock engine and the real engine are interchangeable from the UI's view.

export type StimulusType = 'creative' | 'website' | 'offer' | 'idea'

export interface Stimulus {
  type: StimulusType
  title: string
  /** Normalized text brief the agents read (for images: vision-model description). */
  brief: string
  /** Optional data URL of an uploaded image (creative). */
  imageUrl?: string
  /** Website URL, if type === 'website'. */
  url?: string
  /** Offer fields, if type === 'offer'. */
  offer?: { product: string; price: string; discount: string; urgency: string; terms: string }
  targetAudience: string
}

export type ProfessionGroup =
  | 'Engineering' | 'Design' | 'Marketing' | 'Finance' | 'Operations'
  | 'Healthcare' | 'Education' | 'Retail & Service' | 'Students' | 'Executives'

export type Ideology = 'Progressive' | 'Moderate' | 'Conservative' | 'Libertarian'
export type EconomicStance = 'Frugal' | 'Value-seeking' | 'Premium'
export type TechAdoption = 'Innovator' | 'Early adopter' | 'Early majority' | 'Late majority' | 'Laggard'
export type IncomeBand = 'Low' | 'Lower-middle' | 'Middle' | 'Upper-middle' | 'High'
export type AgeBand = '18-24' | '25-34' | '35-44' | '45-54' | '55+'
export type DecisionRole = 'Buyer' | 'User' | 'Influencer' | 'Gatekeeper' | 'Investor'

export interface Persona {
  id: number
  name: string
  profession: string
  professionGroup: ProfessionGroup
  ageBand: AgeBand
  income: IncomeBand
  ideology: Ideology
  economic: EconomicStance
  tech: TechAdoption
  region: string
  role: DecisionRole
  /** Big Five, 0..1 */
  traits: { openness: number; conscientiousness: number; extraversion: number; agreeableness: number; neuroticism: number }
  /** 0..1, heavy-tailed. Drives feed exposure and persuasion. */
  influence: number
  /** 0..1 */
  activity: number
}

export interface Verdict {
  agentId: number
  /** 0..10 */
  score: number
  intent: 'Would buy/use' | 'Maybe' | 'Would not'
  objection: string
  missing: string
  reaction: string
}

export type SimEvent =
  | { kind: 'stage'; stage: Stage; t: number }
  | { kind: 'impression'; agentId: number; score: number; t: number }
  | { kind: 'post'; id: number; agentId: number; text: string; score: number; round: number; t: number }
  | { kind: 'reply'; id: number; agentId: number; toAgentId: number; toPostId: number; text: string; score: number; round: number; t: number }
  | { kind: 'repost'; agentId: number; fromAgentId: number; postId: number; round: number; t: number }
  /** An agent saw another agent's post in their feed (no action taken). */
  | { kind: 'exposure'; agentId: number; fromAgentId: number; round: number; t: number }
  | { kind: 'mind_change'; agentId: number; from: number; to: number; causedBy: number; round: number; t: number }
  | { kind: 'round'; round: number; totalRounds: number; t: number }
  | { kind: 'expert'; name: string; role: string; finding: string; t: number }
  | { kind: 'done'; t: number }

export type Stage = 'idle' | 'impressions' | 'social' | 'experts' | 'judge' | 'done'

export interface DimensionScore { name: string; score: number; weight: number; note: string }
export interface SegmentScore { segment: string; group: string; score: number; n: number; intent: number }
export interface Objection { text: string; count: number; influence: number; quotes: { agent: string; text: string }[] }
export interface MissingKpi { kpi: string; why: string; target: string }
export interface Variant { label: string; change: string; predictedDelta: number }

export interface Scorecard {
  overall: number
  verdict: string
  summary: string
  dimensions: DimensionScore[]
  segments: SegmentScore[]
  objections: Objection[]
  missing: string[]
  missingKpis: MissingKpi[]
  variants: Variant[]
  polarization: number
  shift: number
  confidence: { sample: number; agreement: number; label: string; note: string }
  intentSplit: { buy: number; maybe: number; no: number }
}
