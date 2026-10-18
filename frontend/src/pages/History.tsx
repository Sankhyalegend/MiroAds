import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type RunSummary } from '../api'

const col = (s: number) => s >= 7 ? '#3ddc97' : s >= 5 ? '#f5c242' : '#ff6b6b'

export default function History() {
  const nav = useNavigate()
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.listRuns().then(setRuns).catch(e => setErr(String(e.message))) }, [])
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 fade-in">
      <h1 className="text-2xl font-bold mb-4">Run history</h1>
      {err && <div className="text-neg text-sm">Backend not reachable: {err}</div>}
      {runs && runs.length === 0 && <div className="text-muted">No runs yet.</div>}
      <div className="space-y-2">
        {runs?.map(r => (
          <div key={r.id} className="card px-4 py-3 flex items-center gap-4 cursor-pointer hover:border-accent" onClick={() => nav(r.status === 'done' || r.status === 'stopped' ? `/scorecard/${r.id}` : `/run/${r.id}`)}>
            <div className="w-14 text-center">
              <div className="text-xl font-bold" style={{ color: r.overall != null ? col(r.overall) : '#8b96ad' }}>{r.overall != null ? r.overall.toFixed(1) : '–'}</div>
              <div className="text-[10px] text-muted">{r.status}</div>
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-semibold truncate">{r.stimulus.title}</div>
              <div className="text-xs text-muted">{r.stimulus.type} · {r.config.crowdSize} agents · {r.config.rounds} rounds · ${r.costUsd.toFixed(3)} · {new Date(r.createdAt * 1000).toLocaleString()}</div>
              {r.verdict && <div className="text-xs mt-0.5">{r.verdict}</div>}
            </div>
            <div className="text-xs text-muted">{r.id}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
