import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, RotateCcw, Download, AlertTriangle, Target, FlaskConical, Quote, Microscope, Users, Store, Mic, Eye, FileText, MousePointerClick, ShoppingCart, GitBranch, ArrowLeftRight } from 'lucide-react'
import { useStore } from '../store'
import { api } from '../api'
import type { Attention, InterviewSummary, PriceTest, Research, Stimulus } from '../types'

const col = (s: number) => s >= 7 ? '#3ddc97' : s >= 5 ? '#f5c242' : '#ff6b6b'

export default function Scorecard() {
  const nav = useNavigate()
  const { id } = useParams()
  const { scorecard: storeSc, stimulus: storeStim, reset, loadRun, runId, market: storeMarket, engine } = useStore()
  const [group, setGroup] = useState('Profession')
  const [metric, setMetric] = useState<'score' | 'stop' | 'click'>('score')
  const [loaded, setLoaded] = useState<{ sc: typeof storeSc; stim: typeof storeStim } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // The brief as the crowd read it (with file descriptions) is saved on the run, not in the form state.
  const liveId = id ?? (engine === 'live' ? runId : null)
  const [seen, setSeen] = useState<Stimulus | null>(null)
  useEffect(() => { if (liveId) api.getRun(liveId).then(r => setSeen(r.stimulus)).catch(() => {}) }, [liveId])

  useEffect(() => {
    if (!id) { if (!storeSc) nav('/'); return }
    if (runId === id && storeSc) return
    Promise.all([api.getScorecard(id), api.getRun(id)]).then(([sc, run]) => { setLoaded({ sc, stim: run.stimulus }); loadRun(id).catch(() => {}) })
      .catch(e => setErr(String(e.message)))
  }, [id, storeSc, runId, nav, loadRun])

  const sc = (id && runId !== id ? loaded?.sc : storeSc) ?? loaded?.sc ?? storeSc
  const stimulus = (id && runId !== id ? loaded?.stim : storeStim) ?? loaded?.stim ?? storeStim
  if (err) return <div className="p-8 text-center text-neg">Could not load scorecard: {err}</div>
  if (!sc || !stimulus) return <div className="p-8 text-center text-muted">Loading scorecard…</div>

  const groups = [...new Set(sc.segments.map(s => s.group))]
  const segs = sc.segments.filter(s => s.group === group)
  const R = sc.research
  // Live reports carry the scan in research.market; the mock engine only streams it as an event.
  const mk: Research['market'] | null = R?.market
    ?? (storeMarket ? { status: storeMarket.status, reason: storeMarket.reason, moodShifts: storeMarket.moodShifts, ...storeMarket.brief } : null)
  const download = () => {
    const blob = new Blob([JSON.stringify({ stimulus, scorecard: sc }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `scorecard-${stimulus.title.replace(/\W+/g, '-')}.json`; a.click()
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 fade-in space-y-5">
      <div className="flex items-center gap-3">
        <button className="btn btn-ghost text-xs" onClick={() => nav(id ? `/run/${id}` : '/run')}><ArrowLeft size={14} /> Back to run</button>
        <div className="min-w-0">
          <div className="text-xs text-muted uppercase tracking-wide">{stimulus.type} · research report{id ? ` · ${id}` : ''}</div>
          <h1 className="text-2xl font-bold truncate">{stimulus.title}</h1>
        </div>
        <div className="ml-auto flex flex-wrap justify-end gap-2">
          {liveId && R?.crowd?.sameCrowdAs && (
            <button className="btn text-xs" onClick={() => nav(`/compare/${R.crowd!.sameCrowdAs}/${liveId}`)}><ArrowLeftRight size={14} /> Compare with first version</button>
          )}
          {liveId && <button className="btn btn-ghost text-xs" onClick={() => nav(`/?from=${liveId}`)} title="Change something and test it on these same people"><GitBranch size={14} /> Test a new version</button>}
          <button className="btn btn-ghost text-xs" onClick={download}><Download size={14} /> Export JSON</button>
          <button className="btn btn-ghost text-xs" onClick={() => { reset(); nav('/') }}><RotateCcw size={14} /> New run</button>
        </div>
      </div>

      <div className="grid md:grid-cols-[220px_1fr] gap-5">
        <div className="card p-5 flex flex-col items-center justify-center text-center">
          <Gauge value={sc.overall} />
          <div className="mt-2 font-semibold" style={{ color: col(sc.overall) }}>{sc.verdict}</div>
          {sc.crowdMean != null && sc.analystScore != null && (
            <div className="text-xs text-muted mt-1">Crowd mean <b className="text-text">{sc.crowdMean.toFixed(1)}</b> · research team <b className="text-text">{sc.analystScore.toFixed(1)}</b></div>
          )}
          <div className="text-xs text-muted mt-1">Confidence: {sc.confidence.label} · {sc.confidence.sample.toLocaleString()} agents · {sc.confidence.agreement}% agreement</div>
        </div>
        <div className="card p-5 space-y-3">
          <p className="leading-relaxed">{sc.summary}</p>
          <div className="grid grid-cols-3 gap-3 text-center">
            <Mini label="Would buy / back" value={`${sc.intentSplit.buy}%`} c="#3ddc97" />
            <Mini label="On the fence" value={`${sc.intentSplit.maybe}%`} c="#f5c242" />
            <Mini label="Would not" value={`${sc.intentSplit.no}%`} c="#ff6b6b" />
          </div>
          <div className="text-[11px] text-muted -mt-1">
            {sc.intentSource ? `What they said they would do, from ${sc.intentSource}.` : 'Estimated from score cut-offs (older report, before exit interviews).'}
          </div>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="bg-panel-2 rounded-lg p-3"><div className="text-xs text-muted">Polarization (std-dev)</div><div className="font-semibold">{sc.polarization.toFixed(2)} <span className="text-xs text-muted font-normal">{sc.polarization > 2.4 ? 'divisive' : sc.polarization > 1.6 ? 'mixed' : 'consensus'}</span></div></div>
            <div className="bg-panel-2 rounded-lg p-3"><div className="text-xs text-muted">Shift during discussion</div><div className="font-semibold" style={{ color: sc.shift >= 0 ? '#3ddc97' : '#ff6b6b' }}>{sc.shift >= 0 ? '+' : ''}{sc.shift.toFixed(2)} <span className="text-xs text-muted font-normal">{R ? `${R.mindChanges} mind changes` : ''}</span></div></div>
            {R && <div className="bg-panel-2 rounded-lg p-3"><div className="text-xs text-muted">Crowd diversity</div><div className="font-semibold capitalize" style={{ color: R.diversity.verdict === 'healthy' ? '#3ddc97' : '#f5c242' }}>{R.diversity.verdict} <span className="text-xs text-muted font-normal">{R.diversity.distinctObjections} distinct objections</span></div></div>}
          </div>
        </div>
      </div>

      {sc.attention && <AttentionCard at={sc.attention} />}
      {sc.interviews?.likelihood && <BuyingCard iv={sc.interviews} />}

      <details className="card p-5">
        <summary className="cursor-pointer font-semibold flex flex-wrap items-center gap-2 list-none">
          <Eye size={16} className="text-accent" /> What the crowd saw
          <span className="text-xs text-muted font-normal">the brief every person read, including what the AI read from your files</span>
        </summary>
        <p className="text-sm text-muted leading-relaxed whitespace-pre-wrap mt-3">{(seen ?? stimulus).brief}</p>
        {(seen ?? stimulus).attachments?.length ? (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {(seen ?? stimulus).attachments!.map(a => <span key={a.name} className="chip inline-flex items-center gap-1"><FileText size={11} /> {a.name}</span>)}
          </div>
        ) : null}
        <div className="text-xs mt-3"><span className="text-muted">Audience: </span>{stimulus.targetAudience || 'not given'}</div>
        {R?.crowd && (
          <div className="text-xs mt-1">
            <span className="text-muted">Crowd: </span>#{R.crowd.seed} · {sc.confidence.sample.toLocaleString()} people
            {R.crowd.sameCrowdAs
              ? <>, the same people as the <Link className="text-accent hover:underline" to={`/scorecard/${R.crowd.sameCrowdAs}`}>first version</Link> (A/B test)</>
              : <> drawn from a village of {R.crowd.village.toLocaleString()} · {R.crowd.newPeople >= sc.confidence.sample ? 'none of them in an earlier test' : `${R.crowd.newPeople.toLocaleString()} new to testing, the rest least tested so far`}</>}
          </div>
        )}
      </details>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="card p-5">
          <h2 className="font-semibold mb-3">Dimension scores</h2>
          <div className="space-y-2.5">
            {sc.dimensions.map(d => (
              <div key={d.name}>
                <div className="flex justify-between text-sm"><span>{d.name} <span className="text-xs text-muted">×{d.weight}</span></span><span className="font-semibold" style={{ color: col(d.score) }}>{d.score.toFixed(1)}</span></div>
                <div className="h-2 bg-panel-2 rounded-full mt-1 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${d.score * 10}%`, background: col(d.score) }} /></div>
                {d.note && <div className="text-[11px] text-muted mt-0.5">{d.note}</div>}
              </div>
            ))}
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3 gap-2">
            <h2 className="font-semibold">By segment</h2>
            <select className="input input-sm" value={group} onChange={e => setGroup(e.target.value)} aria-label="Segment">
              {groups.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
          {segs.some(s => s.stop != null) && (
            <div className="flex gap-1 mb-3 text-xs">
              <span className="text-muted mr-1 self-center">Show:</span>
              {([['score', 'Score'], ['stop', 'Would stop'], ['click', 'Would click']] as const).map(([k, l]) => <button key={k} className="tab py-0.5 px-2" data-active={metric === k} onClick={() => setMetric(k)}>{l}</button>)}
            </div>
          )}
          <div className="space-y-2">
            {segs.map(s => {
              const pct = metric === 'score' ? s.score * 10 : (s[metric] ?? 0)
              const c = col(pct / 10)
              return (
                <div key={s.segment} className="flex items-center gap-3 text-sm">
                  <div className="w-36 truncate" title={s.segment}>{s.segment}</div>
                  <div className="flex-1 h-2 bg-panel-2 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: `${pct}%`, background: metric === 'score' ? c : '#5b8cff' }} /></div>
                  <div className="w-10 text-right font-semibold" style={{ color: metric === 'score' ? c : undefined }}>{metric === 'score' ? s.score.toFixed(1) : `${s[metric] ?? 0}%`}</div>
                  <div className="w-24 text-right text-xs text-muted">{s.intent}% buy · n={s.n}</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="card p-5">
          <h2 className="font-semibold mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-neg" /> Top objections <span className="text-xs text-muted font-normal">{R?.groupedBy?.objections === 'model' ? 'grouped by meaning' : 'clustered by shared words'} · ranked by frequency × influence</span></h2>
          <div className="space-y-3">
            {sc.objections.map((o, i) => (
              <div key={o.text + i} className="bg-panel-2 rounded-lg p-3">
                <div className="flex items-start gap-2"><span className="text-muted text-sm">{i + 1}.</span>
                  <div className="flex-1">
                    <div className="text-sm font-medium">{o.text}</div>
                    <div className="text-xs text-muted mt-0.5">{o.count} agents · influence {o.influence.toFixed(1)}</div>
                    {o.quotes.slice(0, 2).map(q => <div key={q.agent + q.text} className="text-xs mt-1.5 flex gap-1.5 text-muted"><Quote size={12} className="shrink-0 mt-0.5" /><span>“{q.text}” <span className="opacity-70">— {q.agent}</span></span></div>)}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <h3 className="font-semibold mt-4 mb-2 text-sm">What's missing</h3>
          <div className="flex flex-wrap gap-1.5">{sc.missing.map(m => <span key={m} className="chip">{m}</span>)}</div>
        </div>
        <div className="space-y-5">
          <div className="card p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Target size={16} className="text-accent" /> Missing KPIs <span className="text-xs text-muted font-normal">from the research team</span></h2>
            <div className="space-y-2.5">
              {sc.missingKpis.map((k, i) => (
                <div key={k.kpi + i} className="text-sm">
                  <div className="font-medium flex justify-between gap-3"><span>{k.kpi}</span>{k.target && <span className="text-xs text-muted shrink-0 max-w-[45%] text-right">{k.target}</span>}</div>
                  <div className="text-xs text-muted">{k.why}{'by' in k && (k as { by?: string }).by ? <span className="opacity-70"> — {(k as { by?: string }).by}</span> : null}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="card p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><FlaskConical size={16} className="text-pos" /> What would have been better <span className="text-xs text-muted font-normal">predicted score change</span></h2>
            <div className="space-y-2">
              {sc.variants.map(v => (
                <div key={v.label} className="flex items-center gap-3 bg-panel-2 rounded-lg p-3 text-sm">
                  <div className="flex-1"><div className="font-medium">{v.label}</div><div className="text-xs text-muted">{v.change}</div></div>
                  <div className="font-bold" style={{ color: v.predictedDelta >= 0 ? '#3ddc97' : '#ff6b6b' }}>{v.predictedDelta >= 0 ? '+' : ''}{v.predictedDelta.toFixed(1)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {(sc.interviews || (mk && mk.status !== 'off')) && (
        <div className="grid md:grid-cols-2 gap-5">
          {sc.interviews && <Concluded iv={sc.interviews} />}
          {mk && mk.status !== 'off' && <div className="card p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Store size={16} className="text-accent" /> Market context
              <span className="text-xs text-muted font-normal">{mk.status === 'simulated' ? 'simulated, not real market data' : mk.status === 'ok' ? mk.category : 'scan unavailable'}</span></h2>
            {sc.marketPosition && <p className="text-sm leading-relaxed mb-3">{sc.marketPosition}</p>}
            {mk.status === 'unavailable' ? <div className="text-sm text-muted">The agents judged it without knowing the alternatives: {mk.reason}</div> : (
              <>
                {mk.priceRange && <div className="text-xs text-muted mb-2">Price range: <b className="text-text">{mk.priceRange}</b></div>}
                <div className="space-y-1.5">
                  {(mk.competitors ?? []).map(c => (
                    <div key={c.name} className="flex justify-between gap-3 text-sm min-w-0">
                      <span className="truncate shrink-0 max-w-[55%]">{c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="hover:underline">{c.name}</a> : c.name} <span className="text-xs text-muted">{c.maker}</span></span>
                      <span className="text-accent font-semibold truncate text-right" title={c.price}>{c.price}</span>
                    </div>
                  ))}
                </div>
                {(mk.news?.length ?? 0) > 0 && (
                  <>
                    <div className="text-xs text-muted uppercase tracking-wide mt-3 mb-1">In the news</div>
                    {mk.news!.slice(0, 4).map(n => (
                      <div key={n.headline} className="text-xs mt-1">
                        <span style={{ color: n.tone === 'positive' ? '#3ddc97' : n.tone === 'negative' ? '#ff6b6b' : '#8b96ad' }}>●</span> {n.headline} <span className="text-muted">({n.source}, {n.date})</span>
                      </div>
                    ))}
                  </>
                )}
                {mk.moodShifts && (mk.moodShifts.wary || mk.moodShifts.excited) ? <div className="text-xs text-muted mt-2">The news made {mk.moodShifts.wary ?? 0} agents wary and {mk.moodShifts.excited ?? 0} excited before they judged it.</div> : null}
              </>
            )}
          </div>}
        </div>
      )}

      {R && (
        <div className="card p-5 space-y-4">
          <h2 className="font-semibold flex items-center gap-2"><Microscope size={16} className="text-accent" /> Research team notes</h2>
          <div className="grid md:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs text-muted uppercase tracking-wide mb-1">Methodology</div>
              <p className="text-muted leading-relaxed">{R.methodology}</p>
              <div className="text-xs text-muted uppercase tracking-wide mt-3 mb-1">Limitations</div>
              <ul className="list-disc pl-5 text-muted space-y-0.5">{R.limitations.map(l => <li key={l}>{l}</li>)}</ul>
              <div className="text-xs text-muted mt-3">{sc.confidence.note}</div>
              {R.provider && <div className="text-xs text-muted mt-1">Engine: {R.provider} · crowd {R.models?.crowd} · analysts {R.models?.analyst} · cost ${R.costUsd.toFixed(3)}</div>}
            </div>
            <div>
              <div className="text-xs text-muted uppercase tracking-wide mb-1 flex items-center gap-1"><Users size={12} /> Sample composition (n={String(R.composition.n)})</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                {(['professionGroup', 'income', 'gdpTier', 'ideology', 'trust', 'temperament', 'lifeStage', 'settlement', 'adReceptivity'] as const).map(k => {
                  const v = R.composition[k] as Record<string, number> | undefined
                  if (!v) return null
                  return <div key={k}><span className="text-muted capitalize">{k.replace(/([A-Z])/g, ' $1')}: </span>{Object.entries(v).slice(0, 5).map(([a, b]) => `${a} ${b}`).join(', ')}</div>
                })}
              </div>
            </div>
          </div>
          <div>
            <div className="text-xs text-muted uppercase tracking-wide mb-2">Team headlines</div>
            <div className="grid md:grid-cols-3 gap-2">
              {R.team.map(e => (
                <div key={e.name} className="bg-panel-2 rounded-lg p-3 text-xs">
                  <div className="font-semibold text-sm">{e.name}</div>
                  <div className="mt-1">{e.headline}</div>
                  {e.findings.filter(f => f.type !== 'missing_kpi').slice(0, 2).map(f => <div key={f.title} className="mt-1.5 text-muted"><span className="chip mr-1">{f.type.replace(/_/g, ' ')}</span>{f.title}: {f.detail}</div>)}
                </div>
              ))}
            </div>
          </div>
          {R.topPosts.length > 0 && (
            <div>
              <div className="text-xs text-muted uppercase tracking-wide mb-2">Most discussed posts</div>
              <div className="space-y-1.5">
                {R.topPosts.slice(0, 6).map(p => <div key={p.id} className="text-xs bg-panel-2 rounded-md px-3 py-2"><span className="font-semibold">{p.author}</span> <span className="text-muted">· {p.profession}, {p.region} · r{p.round} · {p.replies} replies, {p.reposts} reposts{p.likes != null ? `, ${p.likes} likes` : ''}</span><div className="mt-0.5">“{p.text}”</div></div>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Gauge({ value }: { value: number }) {
  const r = 70, c = 2 * Math.PI * r, pct = value / 10
  return (
    <svg width={180} height={180} viewBox="0 0 180 180">
      <circle cx={90} cy={90} r={r} stroke="#243049" strokeWidth={14} fill="none" />
      <circle cx={90} cy={90} r={r} stroke={col(value)} strokeWidth={14} fill="none" strokeLinecap="round" strokeDasharray={`${c * pct} ${c}`} transform="rotate(-90 90 90)" />
      <text x={90} y={84} textAnchor="middle" fill="#e6ebf5" fontSize={40} fontWeight={700}>{value.toFixed(1)}</text>
      <text x={90} y={108} textAnchor="middle" fill="#8b96ad" fontSize={12}>out of 10</text>
    </svg>
  )
}

/** First impressions where each person really meets it: did they stop, what did they take in, would they click. */
function AttentionCard({ at }: { at: Attention }) {
  const top = Math.max(1, ...at.byPlacement.map(p => p.stopRate))
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3 flex flex-wrap items-center gap-2"><MousePointerClick size={16} className="text-accent" /> Would they even notice it?
        <span className="text-xs text-muted font-normal">each person met it where they usually see ads · {at.n.toLocaleString()} people</span></h2>
      <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-5">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-center">
            <Mini label="Would stop scrolling" value={`${at.stopRate}%`} c={at.stopRate >= 30 ? '#3ddc97' : at.stopRate >= 15 ? '#f5c242' : '#ff6b6b'} />
            <Mini label={`Would click (+${at.click.maybe}% maybe)`} value={`${at.click.yes}%`} c={at.click.yes >= 10 ? '#3ddc97' : at.click.yes >= 4 ? '#f5c242' : '#ff6b6b'} />
          </div>
          {at.glance.length > 0 && (
            <div>
              <div className="text-xs text-muted uppercase tracking-wide mb-1.5">What they took in within 2 seconds</div>
              <div className="space-y-1.5">
                {at.glance.slice(0, 4).map((g, i) => (
                  <div key={g.text + i} className="bg-panel-2 rounded-lg px-2.5 py-1.5 text-sm">
                    {g.text} <span className="text-xs text-muted">· {g.count}</span>
                    {g.quotes[0] && g.quotes[0].text !== g.text && <div className="text-xs text-muted">“{g.quotes[0].text}” — {g.quotes[0].agent}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div>
          <div className="text-xs text-muted uppercase tracking-wide mb-1.5">By where they saw it</div>
          <div className="space-y-1.5">
            {at.byPlacement.map(p => (
              <div key={p.placement} className="flex items-center gap-2 text-sm">
                <div className="w-44 max-sm:w-28 truncate shrink-0" title={p.placement}>{p.placement}</div>
                <div className="flex-1 min-w-8 h-2 bg-panel-2 rounded-full overflow-hidden"><div className="h-full rounded-full bg-accent" style={{ width: `${(p.stopRate / top) * 100}%` }} /></div>
                <div className="text-right text-xs whitespace-nowrap"><b>{p.stopRate}%</b> stop · {p.clickRate}% click</div>
                <div className="w-11 text-right text-xs text-muted shrink-0">n={p.n}</div>
              </div>
            ))}
          </div>
          <div className="text-[11px] text-muted mt-2">Placements come from each person's media habits; small groups (n under 10) are noisy.</div>
        </div>
      </div>
    </div>
  )
}

const LIKELIHOOD_BINS = ['0', '1-2', '3-4', '5', '6-7', '8-9', '10']

/** Purchase likelihood, choice share and the price test from the exit interviews. */
function BuyingCard({ iv }: { iv: InterviewSummary }) {
  const lk = iv.likelihood!, ch = iv.choice, pr = iv.price
  const peak = Math.max(1, ...lk.dist)
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3 flex flex-wrap items-center gap-2"><ShoppingCart size={16} className="text-pos" /> Would they buy it?{pr ? ' At what price?' : ''}
        <span className="text-xs text-muted font-normal">exit interviews · {iv.n.toLocaleString()} people</span></h2>
      <div className="grid md:grid-cols-3 gap-5">
        <div>
          <div className="grid grid-cols-2 gap-2 text-center">
            <Mini label="Likelihood to buy (0-10)" value={lk.mean.toFixed(1)} c={lk.mean >= 6 ? '#3ddc97' : lk.mean >= 4 ? '#f5c242' : '#ff6b6b'} />
            <Mini label="Expected buyers, as stated" value={`${lk.expectedBuyers}%`} c="#e6ebf5" />
          </div>
          <div className="flex items-end gap-1 h-14 mt-3">
            {lk.dist.map((c, i) => (
              <div key={i} className="flex-1 flex flex-col items-center justify-end h-full" title={`${c} said ${LIKELIHOOD_BINS[i]}`}>
                <div className="w-full rounded-t bg-accent/70" style={{ height: `${(c / peak) * 100}%`, minHeight: c ? 2 : 0 }} />
                <div className="text-[9px] text-muted mt-0.5">{LIKELIHOOD_BINS[i]}</div>
              </div>
            ))}
          </div>
          <div className="text-[11px] text-muted mt-1">{lk.top2}% said 8-10. People overstate: real conversion usually lands well below the stated figure.</div>
        </div>
        {ch && (
          <div>
            <div className="text-xs text-muted uppercase tracking-wide mb-1.5">If they had to choose today</div>
            <div className="flex h-3 rounded-full overflow-hidden">
              <div style={{ width: `${ch.this}%`, background: '#3ddc97' }} /><div style={{ width: `${ch.alternative}%`, background: '#f5c242' }} /><div style={{ width: `${ch.neither}%`, background: '#3a4660' }} />
            </div>
            <div className="text-xs mt-2 space-y-0.5">
              <div><span style={{ color: '#3ddc97' }}>●</span> This one <b>{ch.this}%</b></div>
              <div><span style={{ color: '#f5c242' }}>●</span> The alternative they named <b>{ch.alternative}%</b></div>
              <div><span className="text-muted">●</span> Neither <b>{ch.neither}%</b></div>
            </div>
            {iv.alternatives.length > 0 && <div className="text-[11px] text-muted mt-2">Alternatives named most: {iv.alternatives.slice(0, 3).map(a => a.name).join(', ')}</div>}
          </div>
        )}
        {pr ? <PriceRange pr={pr} /> : <div className="text-sm text-muted">No price was shown, so the price questions were skipped. Add a price to the brief to test it.</div>}
      </div>
    </div>
  )
}

function PriceRange({ pr }: { pr: PriceTest }) {
  const fmt = (x: number) => `${pr.currency}${x.toLocaleString()}`
  const pts = [pr.range[0], pr.range[1], pr.optimal, ...(pr.shown != null ? [pr.shown] : [])]
  const lo = Math.min(...pts) * 0.85, hi = Math.max(...pts) * 1.1
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`
  return (
    <div>
      <div className="text-xs text-muted uppercase tracking-wide mb-1.5">Price test</div>
      <div className="text-sm">Acceptable range <b>{fmt(pr.range[0])}–{fmt(pr.range[1])}</b> · best price <b>{fmt(pr.optimal)}</b></div>
      <div className="relative h-8 mt-3 mb-1">
        <div className="absolute top-3 left-0 right-0 h-2 rounded-full bg-panel-2" />
        <div className="absolute top-3 h-2 rounded-full bg-pos/60" style={{ left: x(pr.range[0]), width: `calc(${x(pr.range[1])} - ${x(pr.range[0])})` }} />
        <div className="absolute top-1.5 w-0.5 h-5 bg-pos" style={{ left: x(pr.optimal) }} title={`Best price ${fmt(pr.optimal)}`} />
        {pr.shown != null && <div className="absolute top-0.5 w-0.5 h-7 bg-neg" style={{ left: x(pr.shown) }} title={`Shown price ${fmt(pr.shown)}`} />}
      </div>
      {pr.shown != null && (
        <div className="text-xs"><span className="text-neg">|</span> At the shown {fmt(pr.shown)}: <b>{pr.tooExpensiveAtShown}%</b> say too expensive, {pr.bargainAtShown}% a bargain.</div>
      )}
      <div className="text-[11px] text-muted mt-1">Van Westendorp price questions, {pr.n} consistent answers{pr.dropped ? ` (${pr.dropped} out of order left out)` : ''}.</div>
    </div>
  )
}

/** Exit interviews: what the crowd concluded once the discussion was over. */
function Concluded({ iv }: { iv: InterviewSummary }) {
  const v = iv.vsAlternatives
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3 flex items-center gap-2"><Mic size={16} className="text-pos" /> What the crowd concluded <span className="text-xs text-muted font-normal">exit interviews · {iv.n.toLocaleString()} agents</span></h2>
      <div className="grid grid-cols-3 gap-2 text-center mb-3">
        <Mini label="NPS (recommend 9-10 minus 0-6)" value={`${iv.nps > 0 ? '+' : ''}${iv.nps}`} c={iv.nps >= 0 ? '#3ddc97' : '#ff6b6b'} />
        <Mini label="Changed mind: up / down" value={`${iv.changedMind.positive}% / ${iv.changedMind.negative}%`} c="#e6ebf5" />
        <Mini label="Say it beats what they use" value={`${v.better}%`} c={v.better >= v.worse ? '#3ddc97' : '#f5c242'} />
      </div>
      <div className="text-xs text-muted mb-2">Versus what they use or know: better {v.better}% · same {v.same}% · worse {v.worse}% · know none {v.unknown}%</div>
      {iv.alternatives.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3"><span className="text-xs text-muted">Would choose instead:</span>{iv.alternatives.map(a => <span key={a.name} className="chip">{a.name} · {a.count}</span>)}</div>
      )}
      <div className="text-xs text-muted uppercase tracking-wide mb-1.5">What they concluded</div>
      <div className="space-y-2">
        {/* A theme sorted by the model has a written label and an example quote; a word-matched one is labelled with one member's words. */}
        {iv.themes.slice(0, 4).map(t => (
          <div key={t.text} className="bg-panel-2 rounded-lg p-2.5 text-sm">
            <span className={t.agent ? '' : 'font-medium'}>{t.agent ? `“${t.text}”` : t.text}</span> <span className="text-xs text-muted">· {t.count} {t.count === 1 ? 'agent' : 'agents'}</span>
            {t.agent ? <div className="text-xs text-muted mt-0.5">— {t.agent}</div>
              : t.quotes[0] && <div className="text-xs text-muted mt-0.5">“{t.quotes[0].text}” — {t.quotes[0].agent}</div>}
          </div>
        ))}
      </div>
      {iv.fixes && iv.fixes.length > 0 && (
        <>
          <div className="text-xs text-muted uppercase tracking-wide mt-3 mb-1.5">What would win the rest over</div>
          <div className="flex flex-wrap gap-1.5">{iv.fixes.map(f => <span key={f.text} className="chip">{f.text} · {f.count}</span>)}</div>
        </>
      )}
    </div>
  )
}

function Mini({ label, value, c }: { label: string; value: string; c: string }) {
  return <div className="bg-panel-2 rounded-lg p-3"><div className="text-xl font-bold" style={{ color: c }}>{value}</div><div className="text-xs text-muted">{label}</div></div>
}
