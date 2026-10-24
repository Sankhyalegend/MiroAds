import { create } from 'zustand'
import type { ChangedMind, Intent, MarketScan, Persona, Scorecard, SimEvent, Stage, Stimulus } from './types'
import { generatePersonas } from './mock/personas'
import { runMockSimulation, getLastScorecard } from './mock/engine'
import { bus } from './mock/bus'
import { api, openEvents, type Health } from './api'

export type Engine = 'mock' | 'live'

export interface FeedItem {
  id: number
  kind: 'post' | 'reply' | 'repost' | 'mind_change' | 'interview' | 'expert' | 'system'
  agentId?: number
  toAgentId?: number
  text: string
  score?: number
  round?: number
  intent?: Intent
  t: number
}

/** An exit-interview answer as streamed (the full interview is in the agent detail). */
export interface InterviewEvent { intent: Intent; recommend: number; changedMind: ChangedMind; quote: string }

/** A post in the agent app, keyed by the backend post id. Replies are posts with `replyTo`. */
export interface AppPost {
  id: number
  agentId: number
  text: string
  score: number
  round: number
  t: number
  replyTo?: number
  replyIds: number[]
  reposts: number
  likes: number
  /** Mind changes attributed to this post. */
  mindsChanged: number
}

interface Counters { impressions: number; posts: number; replies: number; reposts: number; likes: number; mindChanges: number; exposures: number; interviews: number }

interface State {
  engine: Engine
  health: Health | null
  stimulus: Stimulus | null
  crowdSize: number
  rounds: number
  speed: number
  /** Run a market scan (competitors, prices, news) before first impressions. */
  marketScan: boolean
  personas: Persona[]
  runId: string | null
  stage: Stage
  round: number
  totalRounds: number
  counters: Counters
  feed: FeedItem[]
  posts: Record<number, AppPost>
  /** Post ids in arrival order. */
  postOrder: number[]
  market: MarketScan | null
  /** Exit interviews by agent id. */
  interviews: Record<number, InterviewEvent>
  expertFindings: { name: string; role: string; finding: string }[]
  scorecard: Scorecard | null
  running: boolean
  liveMean: number
  costUsd: number
  error: string | null

  setEngine: (e: Engine) => void
  checkBackend: () => Promise<Health | null>
  setStimulus: (s: Stimulus) => void
  setCrowdSize: (n: number) => void
  setRounds: (n: number) => void
  setSpeed: (ms: number) => void
  setMarketScan: (on: boolean) => void
  start: () => Promise<string | null>
  loadRun: (id: string) => Promise<void>
  stop: () => void
  reset: () => void
}

let stopper: { stop: () => void } | null = null
let closeWs: (() => void) | null = null
let feedId = 0
export const live = { scores: new Float32Array(0), sum: 0, n: 0 }

const EMPTY: Counters = { impressions: 0, posts: 0, replies: 0, reposts: 0, likes: 0, mindChanges: 0, exposures: 0, interviews: 0 }

export const useStore = create<State>((set, get) => {
  // ---- shared ingestion: both the mock engine and the WebSocket feed events through here ----
  let pending: SimEvent[] = []
  let flushTimer: number | null = null

  const applyEvents = (evs: SimEvent[]) => {
    const s = get()
    const counters = { ...s.counters }
    const feed = [...s.feed]
    const expertFindings = [...s.expertFindings]
    // Posts are copied on first write in this batch, and only the posts that change get new objects,
    // so memoised post cards in the app view skip re-rendering.
    let posts = s.posts, postOrder = s.postOrder, postsDirty = false
    const touchPosts = () => { if (!postsDirty) { posts = { ...posts }; postOrder = [...postOrder]; postsDirty = true } }
    const bump = (id: number | null | undefined, field: 'reposts' | 'likes' | 'mindsChanged') => {
      if (id == null || !posts[id]) return
      touchPosts(); posts[id] = { ...posts[id], [field]: posts[id][field] + 1 }
    }
    let stage = s.stage, round = s.round, totalRounds = s.totalRounds, costUsd = s.costUsd, error = s.error, running = s.running, market = s.market
    let interviews = s.interviews
    for (const e of evs) {
      switch (e.kind) {
        case 'stage': stage = e.stage; break
        case 'round': round = e.round; totalRounds = e.totalRounds; break
        case 'impression':
          counters.impressions++
          if (live.scores[e.agentId] < 0) { live.sum += e.score; live.n++ } else { live.sum += e.score - live.scores[e.agentId] }
          live.scores[e.agentId] = e.score
          break
        case 'post':
          counters.posts++
          touchPosts(); posts[e.id] = { id: e.id, agentId: e.agentId, text: e.text, score: e.score, round: e.round, t: e.t, replyIds: [], reposts: 0, likes: 0, mindsChanged: 0 }; postOrder.push(e.id)
          feed.push({ id: ++feedId, kind: 'post', agentId: e.agentId, text: e.text, score: e.score, round: e.round, t: e.t }); break
        case 'reply':
          counters.replies++
          touchPosts(); posts[e.id] = { id: e.id, agentId: e.agentId, text: e.text, score: e.score, round: e.round, t: e.t, replyTo: e.toPostId, replyIds: [], reposts: 0, likes: 0, mindsChanged: 0 }; postOrder.push(e.id)
          if (posts[e.toPostId]) posts[e.toPostId] = { ...posts[e.toPostId], replyIds: [...posts[e.toPostId].replyIds, e.id] }
          feed.push({ id: ++feedId, kind: 'reply', agentId: e.agentId, toAgentId: e.toAgentId, text: e.text, score: e.score, round: e.round, t: e.t }); break
        case 'repost':
          counters.reposts++
          bump(e.postId, 'reposts')
          feed.push({ id: ++feedId, kind: 'repost', agentId: e.agentId, toAgentId: e.fromAgentId, text: 'reposted', round: e.round, t: e.t }); break
        case 'like': counters.likes++; bump(e.postId, 'likes'); break
        case 'exposure': counters.exposures++; break
        case 'mind_change':
          counters.mindChanges++
          live.sum += e.to - e.from; live.scores[e.agentId] = e.to
          bump(e.postId, 'mindsChanged')
          feed.push({ id: ++feedId, kind: 'mind_change', agentId: e.agentId, toAgentId: e.causedBy, text: `changed their mind ${e.from.toFixed(1)} → ${e.to.toFixed(1)}`, score: e.to, round: e.round, t: e.t }); break
        case 'interview':
          counters.interviews++
          if (interviews === s.interviews) interviews = { ...interviews }
          interviews[e.agentId] = { intent: e.intent, recommend: e.recommend, changedMind: e.changedMind, quote: e.quote }
          feed.push({ id: ++feedId, kind: 'interview', agentId: e.agentId, text: e.quote, intent: e.intent, t: e.t }); break
        case 'expert':
          expertFindings.push({ name: e.name, role: e.role, finding: e.finding })
          feed.push({ id: ++feedId, kind: 'expert', text: `${e.name} (${e.role}): ${e.finding}`, t: e.t }); break
        case 'crowd_ready':
          feed.push({ id: ++feedId, kind: 'system', text: `Crowd of ${e.n} sampled from the library.`, t: e.t }); break
        case 'market': {
          market = { status: e.status, reason: e.reason, brief: e.brief, moodShifts: e.moodShifts }
          const b = e.brief, ms = e.moodShifts
          const moods = ms && (ms.wary || ms.excited) ? ` The news made ${ms.wary ?? 0} people wary and ${ms.excited ?? 0} excited.` : ''
          const text = e.status === 'off' ? 'Market scan skipped for this run.'
            : e.status === 'unavailable' ? `Market scan unavailable: ${e.reason ?? 'unknown error'}. Agents judge it blind.`
            : `Market scan${e.status === 'simulated' ? ' (simulated)' : ''}: ${b?.competitors.length ?? 0} alternatives and ${b?.news.length ?? 0} news items in ${b?.category ?? 'this category'}.${moods}`
          feed.push({ id: ++feedId, kind: 'system', text, t: e.t }); break
        }
        case 'error':
          error = e.message
          feed.push({ id: ++feedId, kind: 'system', text: `Error: ${e.message}`, t: e.t }); break
        case 'done':
          running = false
          if (e.costUsd != null) costUsd = e.costUsd
          if (s.engine === 'mock') set({ scorecard: getLastScorecard() })
          else if (s.runId && !e.failed) api.getScorecard(s.runId).then(sc => set({ scorecard: sc })).catch(() => { /* retried below */ })
          break
      }
    }
    set({ counters, feed: feed.slice(-250), posts, postOrder, market, interviews, expertFindings, stage, round, totalRounds, costUsd, error, running, liveMean: live.n ? live.sum / live.n : 0 })
  }

  const flush = () => { flushTimer = null; const evs = pending; pending = []; applyEvents(evs) }
  const ingest = (e: SimEvent) => {
    bus.emit(e)
    pending.push(e)
    if (flushTimer == null) flushTimer = window.setTimeout(flush, 80)
  }

  const freshRunState = (personas: Persona[], rounds: number) => {
    live.scores = new Float32Array(personas.length).fill(-1)
    live.sum = 0; live.n = 0
    pending = []
    set({ personas, stage: 'idle', round: 0, totalRounds: rounds, running: true, counters: { ...EMPTY }, feed: [], posts: {}, postOrder: [], market: null, interviews: {}, expertFindings: [], scorecard: null, liveMean: 0, costUsd: 0, error: null })
  }

  const attachWs = (runId: string, fromSeq: number) => {
    closeWs?.()
    closeWs = openEvents(runId, fromSeq,
      (batch) => { for (const e of batch) ingest(e) },
      () => { closeWs = null },
      (msg) => set({ error: msg, running: false }))
  }

  return {
    engine: 'live',
    health: null,
    stimulus: null,
    crowdSize: 300,
    rounds: 5,
    speed: 3500,
    marketScan: true,
    personas: [],
    runId: null,
    stage: 'idle',
    round: 0,
    totalRounds: 0,
    counters: { ...EMPTY },
    feed: [],
    posts: {},
    postOrder: [],
    market: null,
    interviews: {},
    expertFindings: [],
    scorecard: null,
    running: false,
    liveMean: 0,
    costUsd: 0,
    error: null,

    setEngine: (engine) => set({ engine }),
    checkBackend: async () => {
      try { const h = await api.health(); set({ health: h }); return h }
      catch { set({ health: null }); return null }
    },
    setStimulus: (stimulus) => set({ stimulus }),
    setCrowdSize: (crowdSize) => set({ crowdSize }),
    setRounds: (rounds) => set({ rounds }),
    setSpeed: (speed) => set({ speed }),
    setMarketScan: (marketScan) => set({ marketScan }),

    start: async () => {
      const { stimulus, crowdSize, rounds, speed, engine, marketScan } = get()
      if (!stimulus) return null
      stopper?.stop(); closeWs?.(); closeWs = null
      if (engine === 'mock') {
        const personas = generatePersonas(crowdSize, 42)
        freshRunState(personas, rounds)
        set({ runId: null })
        stopper = runMockSimulation({ stimulus, personas, rounds, msPerRound: speed, seed: 7, marketScan, onEvent: ingest })
        return 'mock'
      }
      try {
        const { id: stimulus_id } = await api.createStimulus(stimulus)
        const run = await api.createRun({ stimulus_id, crowdSize, rounds, seed: 42, marketScan })
        freshRunState(run.personas, rounds)
        set({ runId: run.id })
        attachWs(run.id, 0)
        return run.id
      } catch (e) {
        set({ error: (e as Error).message, running: false })
        return null
      }
    },

    loadRun: async (id) => {
      // Re-entrancy guard: the Run page can call this more than once while state is still settling.
      if (get().runId === id) return
      stopper?.stop(); closeWs?.(); closeWs = null
      set({ runId: id, engine: 'live' })
      const run = await api.getRun(id)
      if (get().runId !== id) return // superseded
      freshRunState(run.personas, run.config.rounds)
      set({ runId: id, stimulus: run.stimulus, crowdSize: run.config.crowdSize, rounds: run.config.rounds, running: run.status === 'running' || run.status === 'queued', costUsd: run.costUsd, error: run.error })
      if (run.hasScorecard) api.getScorecard(id).then(sc => set({ scorecard: sc })).catch(() => {})
      // Give the canvas a frame to mount against the sized host before events replay into it.
      await new Promise(r => setTimeout(r, 120))
      attachWs(id, 0)
    },

    stop: () => {
      const { runId, engine } = get()
      stopper?.stop(); stopper = null
      if (engine === 'live' && runId) api.stopRun(runId).catch(() => {})
      set({ running: false })
    },
    reset: () => { stopper?.stop(); stopper = null; closeWs?.(); closeWs = null; set({ stage: 'idle', running: false, scorecard: null, feed: [], posts: {}, postOrder: [], market: null, interviews: {}, personas: [], runId: null, error: null }) },
  }
})
