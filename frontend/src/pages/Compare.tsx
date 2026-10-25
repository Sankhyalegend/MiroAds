import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeftRight, Users, AlertTriangle } from 'lucide-react'
import { api } from '../api'
import type { CompareRow, Comparison, RunBrief } from '../types'

const col = (s: number) => s >= 7 ? '#3ddc97' : s >= 5 ? '#f5c242' : '#ff6b6b'
const VERDICT_COLOR: Record<CompareRow['verdict'], string> = { 'B higher': '#3ddc97', 'A higher': '#ff6b6b', 'no clear difference': '#8b96ad' }

function fmt(v: number, unit: string) {
  if (unit === '%') return `${Math.round(v)}%`
  if (unit === '') return `${v > 0 ? '+' : ''}${Math.round(v)}`
  return v.toFixed(1)
}
function fmtDiff(r: CompareRow) {
  const diff = Math.abs(r.diff) < 0.05 ? 0 : r.diff  // no "-0.0"
  const d = r.unit === 'points' ? diff.toFixed(1) : String(Math.round(diff))
  const m = r.unit === 'points' ? r.margin.toFixed(1) : String(Math.round(r.margin))
  return `${diff > 0 ? '+' : ''}${d}${r.unit === '%' ? ' pts' : ''} ± ${m}`
}

/** Two versions side by side. On the same crowd every person is compared with themselves, so small differences show up. */
export default function Compare() {
  const { a, b } = useParams()
  const [cmp, setCmp] = useState<Comparison | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { if (a && b) api.compare(a, b).then(setCmp).catch(e => setErr(String(e.message))) }, [a, b])
  if (err) return <div className="p-8 text-center text-neg">Could not compare: {err}</div>
  if (!cmp) return <div className="p-8 text-center text-muted">Loading comparison…</div>
  const wins = cmp.rows.filter(r => r.verdict === 'B higher').length, losses = cmp.rows.filter(r => r.verdict === 'A higher').length
  const headline = wins && !losses ? 'The new version does better' : losses && !wins ? 'The first version does better' : wins || losses ? 'Mixed: better on some measures, worse on others' : 'No clear difference between the versions'
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 fade-in space-y-5">
      <div>
        <div className="text-xs text-muted uppercase tracking-wide flex items-center gap-1.5"><ArrowLeftRight size={12} /> A/B test</div>
        <h1 className="text-2xl font-bold">{headline}</h1>
        <div className="text-sm text-muted mt-1 flex items-center gap-1.5">
          <Users size={14} />
          {cmp.paired
            ? `The same ${cmp.people.toLocaleString()} people judged both versions, so each person is compared with themselves.`
            : 'Different people judged each version, so differences are noisier than on the same crowd.'}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Version label="A" run={cmp.a} />
        <Version label="B" run={cmp.b} />
      </div>

      <div className="card p-5 overflow-x-auto">
        <h2 className="font-semibold mb-3">Measure by measure <span className="text-xs text-muted font-normal">B minus A, with a 95% margin of error</span></h2>
        <table className="w-full text-sm min-w-[560px]">
          <thead><tr className="text-xs text-muted text-left"><th className="font-normal pb-2">Measure</th><th className="font-normal pb-2 text-right">A</th><th className="font-normal pb-2 text-right">B</th><th className="font-normal pb-2 text-right">B − A</th><th className="font-normal pb-2 text-right">Reading</th></tr></thead>
          <tbody>
            {cmp.rows.map(r => (
              <tr key={r.key} className="border-t border-line">
                <td className="py-2">{r.label}</td>
                <td className="py-2 text-right">{fmt(r.a, r.unit)}</td>
                <td className="py-2 text-right font-semibold">{fmt(r.b, r.unit)}</td>
                <td className="py-2 text-right whitespace-nowrap">{fmtDiff(r)}</td>
                <td className="py-2 text-right"><span className="chip" style={{ borderColor: VERDICT_COLOR[r.verdict], color: VERDICT_COLOR[r.verdict] }}>{r.verdict}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="text-[11px] text-muted mt-2">"No clear difference" means the margin of error covers zero: with this crowd the two versions can't be told apart on that measure.</div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {([['A', cmp.a], ['B', cmp.b]] as const).map(([label, run]) => (
          <div key={label} className="card p-5">
            <h2 className="font-semibold mb-2 flex items-center gap-2"><AlertTriangle size={15} className="text-neg" /> Top objections to {label}</h2>
            <div className="space-y-1.5">
              {run.objections.map(o => <div key={o.text} className="bg-panel-2 rounded-lg px-3 py-2 text-sm">{o.text} <span className="text-xs text-muted">· {o.count}</span></div>)}
              {run.objections.length === 0 && <div className="text-sm text-muted">None recorded.</div>}
            </div>
            {run.price && (
              <div className="text-xs text-muted mt-3">
                Price test: acceptable {run.price.currency}{run.price.range[0]}–{run.price.currency}{run.price.range[1]}, best {run.price.currency}{run.price.optimal}
                {run.price.shown != null ? ` · at ${run.price.currency}${run.price.shown}, ${run.price.tooExpensiveAtShown}% say too expensive` : ''}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function Version({ label, run }: { label: string; run: RunBrief }) {
  return (
    <Link to={`/scorecard/${run.id}`} className="card p-4 flex gap-4 items-center hover:border-accent/60">
      <div className="w-12 h-12 rounded-xl bg-panel-2 grid place-items-center text-xl font-bold shrink-0">{label}</div>
      <div className="min-w-0 flex-1">
        <div className="font-semibold truncate">{run.title}</div>
        {run.verdict && <div className="text-sm truncate">{run.verdict}</div>}
        <div className="text-xs text-muted">{run.n?.toLocaleString() ?? '?'} people · ${run.costUsd.toFixed(2)} · {new Date(run.createdAt * 1000).toLocaleString()}</div>
      </div>
      {run.overall != null && <div className="text-2xl font-bold shrink-0" style={{ color: col(run.overall) }}>{run.overall.toFixed(1)}</div>}
    </Link>
  )
}
