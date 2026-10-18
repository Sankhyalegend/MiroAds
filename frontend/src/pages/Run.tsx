import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Square, BarChart3, Palette, MessageSquare, Repeat2, Sparkles, Eye, Share2 } from 'lucide-react'
import { useStore } from '../store'
import NetworkCanvas, { type EdgeMode } from '../components/NetworkCanvas'
import { GROUP_COLORS, hexToCss } from '../mock/personas'
import type { Stage } from '../types'

const STAGES: { id: Stage; label: string }[] = [
  { id: 'impressions', label: 'First impressions' },
  { id: 'social', label: 'Social rounds' },
  { id: 'experts', label: 'Expert panel' },
  { id: 'judge', label: 'Judge' },
  { id: 'done', label: 'Scorecard' },
]

export default function Run() {
  const nav = useNavigate()
  const { stimulus, personas, stage, round, totalRounds, counters, feed, running, stop, scorecard, liveMean } = useStore()
  const [colorMode, setColorMode] = useState<'sentiment' | 'profession'>('sentiment')
  const [edgeMode, setEdgeMode] = useState<EdgeMode>('all')
  const [net, setNet] = useState({ edges: 0, crossCluster: 0 })
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => { if (!stimulus) nav('/') }, [stimulus, nav])
  useEffect(() => { const el = feedRef.current; if (el) el.scrollTop = el.scrollHeight }, [feed.length])

  if (!stimulus) return null
  const stageIdx = STAGES.findIndex(s => s.id === stage)

  return (
    <div className="h-[calc(100vh-56px)] grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-4 p-4 fade-in">
      <div className="flex flex-col gap-3 min-h-0 min-w-0">
        <div className="card px-4 py-3 flex items-center gap-4 min-w-0 overflow-hidden">
          <div className="min-w-0 shrink">
            <div className="text-xs text-muted uppercase tracking-wide">{stimulus.type}</div>
            <div className="font-semibold truncate">{stimulus.title}</div>
          </div>
          <div className="flex-1 flex items-center gap-1 justify-center min-w-0 overflow-hidden">
            {STAGES.map((s, i) => (
              <div key={s.id} className="flex items-center gap-1">
                <div className={`px-3 py-1 rounded-full text-xs border whitespace-nowrap ${i < stageIdx ? 'border-pos text-pos' : i === stageIdx ? 'border-accent text-text bg-panel-2' : 'border-line text-muted'}`}>
                  {s.label}{s.id === 'social' && stage === 'social' && totalRounds ? ` ${round}/${totalRounds}` : ''}
                </div>
                {i < STAGES.length - 1 && <div className="w-4 h-px bg-line" />}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center rounded-lg border border-line overflow-hidden text-xs">
              {(['all', 'recent', 'off'] as EdgeMode[]).map(m => (
                <button key={m} onClick={() => setEdgeMode(m)}
                  className={`px-2.5 py-1.5 capitalize ${edgeMode === m ? 'bg-panel-2 text-text' : 'text-muted hover:text-text'}`}
                  title="How much of the conversation web to draw">
                  {m === 'all' ? <span className="flex items-center gap-1"><Share2 size={12} /> Lines: all</span> : m}
                </button>
              ))}
            </div>
            <button className="btn btn-ghost text-xs whitespace-nowrap" onClick={() => setColorMode(m => m === 'sentiment' ? 'profession' : 'sentiment')}>
              <Palette size={14} /> {colorMode === 'sentiment' ? 'Colour: sentiment' : 'Colour: profession'}
            </button>
            {running ? (
              <button className="btn btn-ghost text-xs" onClick={stop}><Square size={14} /> Stop</button>
            ) : scorecard ? (
              <button className="btn text-xs" onClick={() => nav('/scorecard')}><BarChart3 size={14} /> View scorecard</button>
            ) : null}
          </div>
        </div>

        <div className="card flex-1 min-h-0 relative">
          <NetworkCanvas personas={personas} colorMode={colorMode} edgeMode={edgeMode} onStats={setNet} />
          <div className="absolute left-3 bottom-3 card px-3 py-2 text-xs flex items-center gap-3 bg-panel/90">
            {colorMode === 'sentiment' ? (
              <>
                <span className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-full bg-neg" /> Against</span>
                <span className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-full bg-neu" /> Undecided</span>
                <span className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-full bg-pos" /> For</span>
                <span className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: '#33405c' }} /> Not yet</span>
              </>
            ) : (
              Object.entries(GROUP_COLORS).slice(0, 10).map(([g, c]) => (
                <span key={g} className="flex items-center gap-1"><i className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: hexToCss(c) }} />{g}</span>
              ))
            )}
            <span className="text-muted">· lines = replies (coloured by stance), reposts (blue), mind changes (white) · faint dashes = reading · scroll to zoom, drag to pan, hover a dot</span>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 min-h-0 min-w-0 max-lg:hidden">
        <div className="card p-4 grid grid-cols-3 gap-3 text-center">
          <Stat icon={<Eye size={14} />} label="Reacted" value={counters.impressions} />
          <Stat icon={<MessageSquare size={14} />} label="Posts + replies" value={counters.posts + counters.replies} />
          <Stat icon={<Repeat2 size={14} />} label="Reposts" value={counters.reposts} />
          <Stat icon={<Sparkles size={14} />} label="Mind changes" value={counters.mindChanges} />
          <Stat icon={<Share2 size={14} />} label="Connections" value={net.edges} />
          <Stat label="Cross-group" value={net.edges ? `${Math.round((net.crossCluster / net.edges) * 100)}%` : '–'} />
          <Stat label="Live mean" value={liveMean ? liveMean.toFixed(1) : '–'} accent={liveMean >= 6.5 ? '#3ddc97' : liveMean >= 4 ? '#f5c242' : '#ff6b6b'} />
          <Stat label="Read events" value={counters.exposures} />
          <Stat label="Crowd" value={personas.length.toLocaleString()} />
        </div>

        <div className="card flex-1 min-h-0 flex flex-col">
          <div className="px-4 py-2 border-b border-line text-xs text-muted uppercase tracking-wide">Live feed</div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-3 space-y-2 text-sm">
            {feed.length === 0 && <div className="text-muted text-xs">Agents are forming first impressions…</div>}
            {feed.slice(-80).map(f => {
              const p = f.agentId != null ? personas[f.agentId] : null
              const to = f.toAgentId != null ? personas[f.toAgentId] : null
              const col = f.score == null ? '#8b96ad' : f.score >= 6.5 ? '#3ddc97' : f.score >= 4 ? '#f5c242' : '#ff6b6b'
              return (
                <div key={f.id} className="fade-in rounded-lg bg-panel-2 px-3 py-2">
                  <div className="flex items-center gap-2 text-xs text-muted">
                    {f.kind === 'expert' ? <span className="chip" style={{ borderColor: '#7c9cff', color: '#7c9cff' }}>expert</span> : (
                      <>
                        <span className="font-semibold text-text">{p?.name}</span>
                        <span>· {p?.profession}</span>
                        {f.kind === 'reply' && to && <span>→ {to.name.split(' ')[0]}</span>}
                        {f.kind === 'repost' && to && <span>↻ {to.name.split(' ')[0]}</span>}
                        {f.kind === 'mind_change' && <span className="chip" style={{ borderColor: '#fff', color: '#fff' }}>mind change</span>}
                        {f.score != null && <span className="ml-auto font-semibold" style={{ color: col }}>{f.score.toFixed(1)}</span>}
                      </>
                    )}
                  </div>
                  <div className="mt-0.5 leading-snug">{f.text}</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function Stat({ icon, label, value, accent }: { icon?: React.ReactNode; label: string; value: number | string; accent?: string }) {
  return (
    <div>
      <div className="text-lg font-bold" style={{ color: accent }}>{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="text-[11px] text-muted flex items-center justify-center gap-1">{icon}{label}</div>
    </div>
  )
}
