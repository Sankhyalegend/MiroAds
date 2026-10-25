import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Image, Globe, Tag, Lightbulb, Plus, ChevronRight } from 'lucide-react'
import { api, type RunSummary } from '../api'

const col = (s: number) => s >= 7 ? '#3ddc97' : s >= 5 ? '#f5c242' : '#ff6b6b'
const TYPE_ICON: Record<string, React.ReactNode> = { creative: <Image size={16} />, website: <Globe size={16} />, offer: <Tag size={16} />, idea: <Lightbulb size={16} /> }

export default function History() {
  const nav = useNavigate()
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.listRuns().then(setRuns).catch(e => setErr(String(e.message))) }, [])
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 fade-in">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-bold">Your tests</h1>
        <button className="btn text-sm ml-auto" onClick={() => nav('/')}><Plus size={15} /> New test</button>
      </div>
      {err && <div className="card p-4 text-neg text-sm">Can't reach the backend: {err}. Start it, then reload this page.</div>}
      {!runs && !err && <div className="text-muted text-sm">Loading…</div>}
      {runs && runs.length === 0 && (
        <div className="card p-8 text-center">
          <div className="font-semibold">No tests yet</div>
          <div className="text-sm text-muted mt-1">Run your first test and it will show up here with its score and verdict.</div>
          <button className="btn mt-4" onClick={() => nav('/')}><Plus size={15} /> Start a test</button>
        </div>
      )}
      <div className="space-y-2">
        {runs?.map(r => (
          <button key={r.id} className="card w-full text-left px-4 py-3 flex items-center gap-4 cursor-pointer" onClick={() => nav(r.status === 'done' || r.status === 'stopped' ? `/scorecard/${r.id}` : `/run/${r.id}`)}>
            <div className="w-14 text-center shrink-0">
              <div className="text-2xl font-bold" style={{ color: r.overall != null ? col(r.overall) : '#8b96ad' }}>{r.overall != null ? r.overall.toFixed(1) : '–'}</div>
              <div className="text-[10px] text-muted">{r.status === 'done' ? 'out of 10' : r.status}</div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-panel-2 grid place-items-center text-muted shrink-0">{TYPE_ICON[r.stimulus.type] ?? null}</div>
            <div className="min-w-0 flex-1">
              <div className="font-semibold truncate flex items-center gap-2">
                <span className="truncate">{r.stimulus.title}</span>
                {r.config.sameCrowdAs && (
                  <span role="link" tabIndex={0} className="chip text-[10px] shrink-0 hover:border-accent" title="Same crowd as an earlier version: open the comparison"
                    onClick={e => { e.stopPropagation(); nav(`/compare/${r.config.sameCrowdAs}/${r.id}`) }}
                    onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); nav(`/compare/${r.config.sameCrowdAs}/${r.id}`) } }}>A/B</span>
                )}
              </div>
              {r.verdict && <div className="text-sm truncate">{r.verdict}</div>}
              <div className="text-xs text-muted">{r.config.crowdSize.toLocaleString()} people · {r.config.rounds} rounds · ${r.costUsd.toFixed(2)} · {new Date(r.createdAt * 1000).toLocaleString()}</div>
            </div>
            <ChevronRight size={16} className="text-muted shrink-0" />
          </button>
        ))}
      </div>
    </div>
  )
}
