import { create } from 'zustand'
import type { Persona, Scorecard, SimEvent, Stage, Stimulus } from './types'
import { generatePersonas } from './mock/personas'
import { runMockSimulation, getLastScorecard } from './mock/engine'
import { bus } from './mock/bus'

export interface FeedItem {
  id: number
  kind: 'post' | 'reply' | 'repost' | 'mind_change' | 'expert'
  agentId?: number
  toAgentId?: number
  text: string
  score?: number
  round?: number
  t: number
}

interface Counters { impressions: number; posts: number; replies: number; reposts: number; mindChanges: number; exposures: number }

interface State {
  stimulus: Stimulus | null
  crowdSize: number
  rounds: number
  speed: number // ms per round
  personas: Persona[]
  stage: Stage
  round: number
  totalRounds: number
  counters: Counters
  feed: FeedItem[]
  expertFindings: { name: string; role: string; finding: string }[]
  scorecard: Scorecard | null
  running: boolean
  liveMean: number

  setStimulus: (s: Stimulus) => void
  setCrowdSize: (n: number) => void
  setRounds: (n: number) => void
  setSpeed: (ms: number) => void
  start: () => void
  stop: () => void
  reset: () => void
}

let stopper: { stop: () => void } | null = null
let feedId = 0
// Live scores live outside React state; the canvas reads them directly.
export const live = { scores: new Float32Array(0), sum: 0, n: 0 }

export const useStore = create<State>((set, get) => ({
  stimulus: null,
  crowdSize: 1000,
  rounds: 5,
  speed: 3500,
  personas: [],
  stage: 'idle',
  round: 0,
  totalRounds: 0,
  counters: { impressions: 0, posts: 0, replies: 0, reposts: 0, mindChanges: 0, exposures: 0 },
  feed: [],
  expertFindings: [],
  scorecard: null,
  running: false,
  liveMean: 0,

  setStimulus: (stimulus) => set({ stimulus }),
  setCrowdSize: (crowdSize) => set({ crowdSize }),
  setRounds: (rounds) => set({ rounds }),
  setSpeed: (speed) => set({ speed }),

  start: () => {
    const { stimulus, crowdSize, rounds, speed } = get()
    if (!stimulus) return
    stopper?.stop()
    const personas = generatePersonas(crowdSize, 42)
    live.scores = new Float32Array(crowdSize).fill(-1)
    live.sum = 0; live.n = 0
    set({
      personas, stage: 'impressions', round: 0, totalRounds: rounds, running: true,
      counters: { impressions: 0, posts: 0, replies: 0, reposts: 0, mindChanges: 0, exposures: 0 },
      feed: [], expertFindings: [], scorecard: null, liveMean: 0,
    })

    // Batch React updates: counters/feed are flushed at ~12fps.
    let pending: SimEvent[] = []
    let flushTimer: number | null = null
    const flush = () => {
      flushTimer = null
      const evs = pending; pending = []
      const s = get()
      const counters = { ...s.counters }
      const feed = [...s.feed]
      const expertFindings = [...s.expertFindings]
      let stage = s.stage, round = s.round, totalRounds = s.totalRounds
      for (const e of evs) {
        switch (e.kind) {
          case 'stage': stage = e.stage; break
          case 'round': round = e.round; totalRounds = e.totalRounds; break
          case 'impression':
            counters.impressions++
            live.scores[e.agentId] = e.score; live.sum += e.score; live.n++
            break
          case 'post':
            counters.posts++
            feed.push({ id: ++feedId, kind: 'post', agentId: e.agentId, text: e.text, score: e.score, round: e.round, t: e.t }); break
          case 'reply':
            counters.replies++
            feed.push({ id: ++feedId, kind: 'reply', agentId: e.agentId, toAgentId: e.toAgentId, text: e.text, score: e.score, round: e.round, t: e.t }); break
          case 'repost':
            counters.reposts++
            feed.push({ id: ++feedId, kind: 'repost', agentId: e.agentId, toAgentId: e.fromAgentId, text: 'reposted', round: e.round, t: e.t }); break
          case 'exposure':
            counters.exposures++; break
          case 'mind_change':
            counters.mindChanges++
            live.sum += e.to - e.from; live.scores[e.agentId] = e.to
            feed.push({ id: ++feedId, kind: 'mind_change', agentId: e.agentId, toAgentId: e.causedBy, text: `changed their mind ${e.from.toFixed(1)} → ${e.to.toFixed(1)}`, score: e.to, round: e.round, t: e.t }); break
          case 'expert':
            expertFindings.push({ name: e.name, role: e.role, finding: e.finding })
            feed.push({ id: ++feedId, kind: 'expert', text: `${e.name} (${e.role}): ${e.finding}`, t: e.t }); break
          case 'done':
            set({ running: false, scorecard: getLastScorecard() })
            break
        }
      }
      set({ counters, feed: feed.slice(-250), expertFindings, stage, round, totalRounds, liveMean: live.n ? live.sum / live.n : 0 })
    }

    stopper = runMockSimulation({
      stimulus, personas, rounds, msPerRound: speed, seed: 7,
      onEvent: (e) => {
        bus.emit(e)
        pending.push(e)
        if (flushTimer == null) flushTimer = window.setTimeout(flush, 80)
      },
    })
  },

  stop: () => { stopper?.stop(); stopper = null; set({ running: false }) },
  reset: () => { stopper?.stop(); stopper = null; set({ stage: 'idle', running: false, scorecard: null, feed: [], personas: [] }) },
}))
