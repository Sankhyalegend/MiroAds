import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, RotateCcw, Download, AlertTriangle, Target, FlaskConical, Quote } from 'lucide-react'
import { useStore } from '../store'

const col = (s: number) => s >= 7 ? '#3ddc97' : s >= 5 ? '#f5c242' : '#ff6b6b'

export default function Scorecard() {
  const nav = useNavigate()
  const { scorecard: sc, stimulus, reset } = useStore()
  const [group, setGroup] = useState('Profession')
  useEffect(() => { if (!sc) nav('/') }, [sc, nav])
  if (!sc || !stimulus) return null

  const groups = [...new Set(sc.segments.map(s => s.group))]
  const segs = sc.segments.filter(s => s.group === group)

  const download = () => {
    const blob = new Blob([JSON.stringify({ stimulus, scorecard: sc }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `scorecard-${stimulus.title.replace(/\W+/g, '-')}.json`; a.click()
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 fade-in space-y-5">
      <div className="flex items-center gap-3">
        <button className="btn btn-ghost text-xs" onClick={() => nav('/run')}><ArrowLeft size={14} /> Back to run</button>
        <div className="min-w-0">
          <div className="text-xs text-muted uppercase tracking-wide">{stimulus.type} · scorecard</div>
          <h1 className="text-2xl font-bold truncate">{stimulus.title}</h1>
        </div>
        <div className="ml-auto flex gap-2">
          <button className="btn btn-ghost text-xs" onClick={download}><Download size={14} /> Export JSON</button>
          <button className="btn btn-ghost text-xs" onClick={() => { reset(); nav('/') }}><RotateCcw size={14} /> New run</button>
        </div>
      </div>

      {/* Headline */}
      <div className="grid md:grid-cols-[220px_1fr] gap-5">
        <div className="card p-5 flex flex-col items-center justify-center text-center">
          <Gauge value={sc.overall} />
          <div className="mt-2 font-semibold" style={{ color: col(sc.overall) }}>{sc.verdict}</div>
          <div className="text-xs text-muted mt-1">Confidence: {sc.confidence.label} · {sc.confidence.sample.toLocaleString()} agents · {sc.confidence.agreement}% agreement</div>
        </div>
        <div className="card p-5 space-y-3">
          <p className="leading-relaxed">{sc.summary}</p>
          <div className="grid grid-cols-3 gap-3 text-center">
            <Mini label="Would buy / back" value={`${sc.intentSplit.buy}%`} c="#3ddc97" />
            <Mini label="On the fence" value={`${sc.intentSplit.maybe}%`} c="#f5c242" />
            <Mini label="Would not" value={`${sc.intentSplit.no}%`} c="#ff6b6b" />
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-panel-2 rounded-lg p-3">
              <div className="text-xs text-muted">Polarization (score std-dev)</div>
              <div className="font-semibold">{sc.polarization.toFixed(2)} <span className="text-xs text-muted font-normal">{sc.polarization > 2.4 ? 'divisive' : sc.polarization > 1.6 ? 'mixed' : 'consensus'}</span></div>
            </div>
            <div className="bg-panel-2 rounded-lg p-3">
              <div className="text-xs text-muted">Opinion shift during discussion</div>
              <div className="font-semibold" style={{ color: sc.shift >= 0 ? '#3ddc97' : '#ff6b6b' }}>{sc.shift >= 0 ? '+' : ''}{sc.shift.toFixed(2)} <span className="text-xs text-muted font-normal">{sc.shift >= 0 ? 'social proof helped' : 'objections spread'}</span></div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        {/* Dimensions */}
        <div className="card p-5">
          <h2 className="font-semibold mb-3">Dimension scores</h2>
          <div className="space-y-2.5">
            {sc.dimensions.map(d => (
              <div key={d.name}>
                <div className="flex justify-between text-sm"><span>{d.name} <span className="text-xs text-muted">×{d.weight}</span></span><span className="font-semibold" style={{ color: col(d.score) }}>{d.score.toFixed(1)}</span></div>
                <div className="h-2 bg-panel-2 rounded-full mt-1 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${d.score * 10}%`, background: col(d.score) }} /></div>
              </div>
            ))}
          </div>
        </div>

        {/* Segments */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">By segment</h2>
            <div className="flex gap-1 flex-wrap justify-end">
              {groups.map(g => <button key={g} className="tab text-xs py-1 px-2" data-active={group === g} onClick={() => setGroup(g)}>{g}</button>)}
            </div>
          </div>
          <div className="space-y-2">
            {segs.map(s => (
              <div key={s.segment} className="flex items-center gap-3 text-sm">
                <div className="w-32 truncate">{s.segment}</div>
                <div className="flex-1 h-2 bg-panel-2 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: `${s.score * 10}%`, background: col(s.score) }} /></div>
                <div className="w-10 text-right font-semibold" style={{ color: col(s.score) }}>{s.score.toFixed(1)}</div>
                <div className="w-20 text-right text-xs text-muted">{s.intent}% buy · n={s.n}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        {/* Objections */}
        <div className="card p-5">
          <h2 className="font-semibold mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-neg" /> Top objections <span className="text-xs text-muted font-normal">ranked by frequency × influence</span></h2>
          <div className="space-y-3">
            {sc.objections.map((o, i) => (
              <div key={o.text} className="bg-panel-2 rounded-lg p-3">
                <div className="flex items-start gap-2">
                  <span className="text-muted text-sm">{i + 1}.</span>
                  <div className="flex-1">
                    <div className="text-sm font-medium">{o.text}</div>
                    <div className="text-xs text-muted mt-0.5">{o.count} agents · influence {o.influence.toFixed(1)}</div>
                    {o.quotes.slice(0, 1).map(q => (
                      <div key={q.agent} className="text-xs mt-1.5 flex gap-1.5 text-muted"><Quote size={12} className="shrink-0 mt-0.5" /><span>“{q.text}” <span className="opacity-70">— {q.agent}</span></span></div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <h3 className="font-semibold mt-4 mb-2 text-sm">What's missing (most cited)</h3>
          <div className="flex flex-wrap gap-1.5">{sc.missing.map(m => <span key={m} className="chip">{m}</span>)}</div>
        </div>

        {/* KPIs + variants */}
        <div className="space-y-5">
          <div className="card p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Target size={16} className="text-accent" /> Missing KPIs <span className="text-xs text-muted font-normal">from the expert panel</span></h2>
            <div className="space-y-2.5">
              {sc.missingKpis.map(k => (
                <div key={k.kpi} className="text-sm">
                  <div className="font-medium flex justify-between gap-3"><span>{k.kpi}</span><span className="text-xs text-muted shrink-0">target: {k.target}</span></div>
                  <div className="text-xs text-muted">{k.why}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="card p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><FlaskConical size={16} className="text-pos" /> What would have been better <span className="text-xs text-muted font-normal">with predicted score change</span></h2>
            <div className="space-y-2">
              {sc.variants.map(v => (
                <div key={v.label} className="flex items-center gap-3 bg-panel-2 rounded-lg p-3 text-sm">
                  <div className="flex-1">
                    <div className="font-medium">{v.label}</div>
                    <div className="text-xs text-muted">{v.change}</div>
                  </div>
                  <div className="font-bold" style={{ color: v.predictedDelta >= 0 ? '#3ddc97' : '#ff6b6b' }}>{v.predictedDelta >= 0 ? '+' : ''}{v.predictedDelta.toFixed(1)}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-muted mt-3">In the LLM engine each variant is re-run through stage 1 on the same crowd, so the delta is measured, not guessed.</div>
          </div>
        </div>
      </div>

      <div className="text-xs text-muted">{sc.confidence.note}</div>
    </div>
  )
}

function Gauge({ value }: { value: number }) {
  const r = 70, c = 2 * Math.PI * r, pct = value / 10
  return (
    <svg width={180} height={180} viewBox="0 0 180 180">
      <circle cx={90} cy={90} r={r} stroke="#243049" strokeWidth={14} fill="none" />
      <circle cx={90} cy={90} r={r} stroke={col(value)} strokeWidth={14} fill="none" strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`} transform="rotate(-90 90 90)" />
      <text x={90} y={84} textAnchor="middle" fill="#e6ebf5" fontSize={40} fontWeight={700}>{value.toFixed(1)}</text>
      <text x={90} y={108} textAnchor="middle" fill="#8b96ad" fontSize={12}>out of 10</text>
    </svg>
  )
}

function Mini({ label, value, c }: { label: string; value: string; c: string }) {
  return <div className="bg-panel-2 rounded-lg p-3"><div className="text-xl font-bold" style={{ color: c }}>{value}</div><div className="text-xs text-muted">{label}</div></div>
}
