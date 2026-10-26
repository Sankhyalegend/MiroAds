import type { AgentDetail, Comparison, Persona, Scorecard, SimEvent, Stimulus } from './types'

export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
// A relative base (/api in the deployed build) means the server the page came from.
const WS_BASE = API_BASE.startsWith('/') ? `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}${API_BASE}` : API_BASE.replace(/^http/, 'ws')

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API_BASE + path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new Error(`${r.status} ${msg}`)
  }
  return r.json() as Promise<T>
}

/** `village`: how many people new runs draw from. */
export interface Health { ok: boolean; provider: string; crowdModel: string; analystModel: string; devMode: boolean; library: number; village?: number; runBudgetUsd: number }
/** `sameCrowdAs`: the run whose people this A/B run reused. */
export interface RunConfig { crowdSize: number; rounds: number; seed?: number; budgetUsd: number; marketScan?: boolean; sameCrowdAs?: string | null }
export interface RunView {
  id: string; status: string; stage: string; costUsd: number; error: string | null
  config: RunConfig
  stimulus: Stimulus; personas: Persona[]; lastSeq: number; hasScorecard: boolean
}
export interface RunSummary { id: string; status: string; stage: string; costUsd: number; createdAt: number; stimulus: { type: string; title: string }; config: RunConfig; overall: number | null; verdict: string | null }

export const api = {
  health: () => j<Health>('/health'),
  libraryStats: () => j<{ count: number; job: { running: boolean; done: number; total: number; cost: number; error: string | null } }>('/library/stats'),
  buildLibrary: (n: number, budgetUsd: number) => j<{ started: boolean; toGenerate: number }>('/library/build', { method: 'POST', body: JSON.stringify({ n, seed: 1, budgetUsd }) }),
  createStimulus: (s: Stimulus) => j<{ id: string }>('/stimuli', { method: 'POST', body: JSON.stringify(s) }),
  createRun: (body: { stimulus_id: string; crowdSize: number; rounds: number; seed?: number; budgetUsd?: number; marketScan?: boolean; sameCrowdAs?: string }) =>
    j<RunView>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  compare: (a: string, b: string) => j<Comparison>(`/compare/${a}/${b}`),
  getRun: (id: string) => j<RunView>(`/runs/${id}`),
  stopRun: (id: string) => j<{ stopped: boolean }>(`/runs/${id}/stop`, { method: 'POST' }),
  getScorecard: (id: string) => j<Scorecard>(`/runs/${id}/scorecard`),
  getAgent: (id: string, aid: number) => j<AgentDetail>(`/runs/${id}/agents/${aid}`),
  listRuns: () => j<RunSummary[]>('/runs'),
}

/** Opens the event stream. Replays from `fromSeq`, then streams live. Returns a closer. */
export function openEvents(runId: string, fromSeq: number, onBatch: (evs: (SimEvent & { seq: number })[]) => void, onEof: () => void, onError?: (e: string) => void): () => void {
  let closed = false
  let ws: WebSocket | null = null
  let last = fromSeq - 1
  let attempts = 0
  const connect = () => {
    if (closed) return
    ws = new WebSocket(`${WS_BASE}/runs/${runId}/events?from_seq=${last + 1}`)
    ws.onmessage = (m) => {
      const data = JSON.parse(m.data) as { batch: (SimEvent & { seq: number })[]; eof?: boolean }
      if (data.batch?.length) { last = data.batch[data.batch.length - 1].seq; onBatch(data.batch) }
      if (data.eof) { closed = true; ws?.close(); onEof() }
    }
    ws.onclose = () => {
      if (closed) return
      attempts++
      if (attempts > 20) { onError?.('connection lost'); return }
      setTimeout(connect, Math.min(5000, 300 * attempts))
    }
    ws.onerror = () => { /* onclose handles retry */ }
  }
  connect()
  return () => { closed = true; ws?.close() }
}
