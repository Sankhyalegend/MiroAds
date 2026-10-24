import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../api'
import { live } from '../store'
import type { AgentDetail, Persona } from '../types'
import { GROUP_COLORS, hexToCss } from '../mock/personas'

const col = (s: number) => s >= 6.5 ? '#3ddc97' : s >= 4 ? '#f5c242' : '#ff6b6b'

export default function AgentPanel({ runId, persona, onClose }: { runId: string | null; persona: Persona; onClose: () => void }) {
  const [detail, setDetail] = useState<AgentDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setDetail(null); setErr(null)
    if (!runId) return
    api.getAgent(runId, persona.id).then(setDetail).catch(e => setErr(String(e.message)))
  }, [runId, persona.id])

  const score = live.scores[persona.id]
  const d = detail ?? (persona as AgentDetail)
  const ex = d.extra ?? {}
  return (
    <div className="card p-4 space-y-3 text-sm fade-in overflow-y-auto">
      <div className="flex items-start gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-base">{persona.name}</div>
          <div className="text-muted text-xs">{persona.profession} · {persona.ageBand} · {persona.region}{d.mood ? ` · feeling ${d.mood}` : ''}</div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-xl font-bold" style={{ color: score < 0 ? '#8b96ad' : col(score) }}>{score < 0 ? '–' : score.toFixed(1)}</div>
          <div className="text-[10px] text-muted">current score</div>
        </div>
        <button className="btn btn-ghost p-1.5" onClick={onClose}><X size={14} /></button>
      </div>
      <div className="flex flex-wrap gap-1">
        <span className="chip" style={{ borderColor: hexToCss(GROUP_COLORS[persona.professionGroup]) }}>{persona.professionGroup}</span>
        <span className="chip">{persona.ideology}</span><span className="chip">{persona.economic}</span><span className="chip">{persona.tech}</span>
        <span className="chip">{persona.income} income</span><span className="chip">{persona.role}</span>
        {ex.trust && <span className="chip">{String(ex.trust)}</span>}{ex.heuristic && <span className="chip">{String(ex.heuristic)}</span>}
        {ex.gdpTier && <span className="chip">{String(ex.gdpTier)}-income country</span>}
      </div>
      {ex.backstory && <p className="text-xs text-muted leading-relaxed">{String(ex.backstory)}</p>}
      {ex.lens && <div className="text-xs"><span className="text-muted">How they judge: </span>{String(ex.lens)}</div>}
      {Array.isArray(ex.petPeeves) && ex.petPeeves.length > 0 && <div className="text-xs"><span className="text-muted">Pet peeves: </span>{(ex.petPeeves as string[]).join('; ')}</div>}

      {d.context && (
        <div className="bg-panel-2 rounded-lg p-3 space-y-1.5">
          <div className="text-xs text-muted uppercase tracking-wide">What they know about the market</div>
          {d.context.moodBefore && <div className="text-xs"><span className="text-muted">Mood: </span><b>{d.mood}</b> (was {d.context.moodBefore}): {d.context.moodReason}</div>}
          {d.context.knows.length > 0
            ? <ul className="text-xs list-disc pl-4 space-y-0.5">{d.context.knows.map(k => <li key={k}>{k}</li>)}</ul>
            : <div className="text-xs text-muted">Doesn't know any similar products.</div>}
          {d.context.newsSeen.map(n => <div key={n} className="text-xs"><span className="text-muted">Read: </span>{n}</div>)}
          {d.context.owns && <div className="text-xs"><span className="text-muted">Already uses: </span>{d.context.owns}</div>}
        </div>
      )}

      {d.verdict ? (
        <div className="bg-panel-2 rounded-lg p-3 space-y-1.5">
          <div className="text-xs text-muted uppercase tracking-wide">First impression · {d.verdict.score.toFixed(1)} · {d.verdict.intent}</div>
          <div>“{d.verdict.reaction}”</div>
          {d.verdict.reasoning && <div className="text-xs text-muted">{d.verdict.reasoning}</div>}
          <div className="text-xs"><span className="text-muted">Objection: </span>{d.verdict.objection}</div>
          <div className="text-xs"><span className="text-muted">Would need: </span>{d.verdict.missing}</div>
          {d.verdict.price_reaction && <div className="text-xs"><span className="text-muted">On price: </span>{d.verdict.price_reaction}</div>}
        </div>
      ) : runId ? (
        <div className="text-xs text-muted">{err ? `Could not load detail: ${err}` : 'Loading reasoning…'}</div>
      ) : (
        <div className="text-xs text-muted">Mock engine: no LLM reasoning for this agent. Switch to the live engine to read why they scored it this way.</div>
      )}

      {d.actions && d.actions.length > 0 && (
        <div>
          <div className="text-xs text-muted uppercase tracking-wide mb-1">What they did</div>
          <div className="space-y-1.5">
            {d.actions.map((a, i) => (
              <div key={i} className="text-xs bg-panel-2 rounded-md px-2.5 py-1.5">
                <span className="text-muted">r{a.round} · {a.action}{a.target ? ` → post ${a.target}` : ''} · </span>
                <span style={{ color: col(a.score) }}>{a.score.toFixed(1)}</span>
                {a.text && <div className="mt-0.5">“{a.text}”</div>}
                {a.why && <div className="text-muted italic">{a.why}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
