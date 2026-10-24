import { memo, useMemo, useState } from 'react'
import { MessageSquare, Repeat2, Heart, Sparkles, Search, Store, Newspaper, Mic } from 'lucide-react'
import { useStore, type AppPost, type InterviewEvent } from '../store'
import { GROUP_COLORS, INTENT_COLOR, PROFESSION_GROUPS, hexToCss } from '../mock/personas'
import type { Intent, Persona } from '../types'

const col = (s: number) => s >= 6.5 ? '#3ddc97' : s >= 4 ? '#f5c242' : '#ff6b6b'
const PAGE = 30

type Sort = 'latest' | 'top'
type Stance = 'all' | 'for' | 'undecided' | 'against'
interface Thread { root: AppPost; replies: AppPost[]; last: number; engagement: number }

const stanceOk = (s: number, st: Stance) => st === 'all' || (st === 'for' ? s >= 6.5 : st === 'against' ? s < 4 : s >= 4 && s < 6.5)

type Tab = 'feed' | 'takes' | 'market'

/** The social app the agents use during the discussion (threads, reposts, likes, who changed whose mind),
 *  what each of them concluded in the exit interview, and what was already on the market when they looked. */
export default function AgentApp({ onSelect }: { onSelect: (agentId: number) => void }) {
  const [tab, setTab] = useState<Tab>('feed')
  const postCount = useStore(s => s.postOrder.length)
  const takeCount = useStore(s => s.counters.interviews)
  const market = useStore(s => s.market)
  const tabs: { id: Tab; label: string; icon: React.ReactNode; note?: string }[] = [
    { id: 'feed', label: 'Feed', icon: <MessageSquare size={13} />, note: postCount ? postCount.toLocaleString() : undefined },
    { id: 'takes', label: 'Final takes', icon: <Mic size={13} />, note: takeCount ? takeCount.toLocaleString() : undefined },
    { id: 'market', label: 'Market', icon: <Store size={13} />, note: market?.status === 'ok' ? `${market.brief?.competitors.length ?? 0} alternatives` : market?.status },
  ]
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="px-3 pt-2 flex items-center gap-1 border-b border-line">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 text-xs flex items-center gap-1.5 border-b-2 -mb-px ${tab === t.id ? 'border-accent text-text' : 'border-transparent text-muted hover:text-text'}`}>
            {t.icon}{t.label}{t.note && <span className="text-muted">· {t.note}</span>}
          </button>
        ))}
      </div>
      {tab === 'feed' ? <Feed onSelect={onSelect} /> : tab === 'takes' ? <FinalTakes onSelect={onSelect} /> : <Market />}
    </div>
  )
}

const TAKES_PAGE = 40

/** Exit interviews: everyone's conclusion once the discussion was over. */
function FinalTakes({ onSelect }: { onSelect: (agentId: number) => void }) {
  const interviews = useStore(s => s.interviews)
  const personas = useStore(s => s.personas)
  const [intent, setIntent] = useState<'all' | Intent>('all')
  const [group, setGroup] = useState('all')
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(TAKES_PAGE)

  const rows = useMemo(() => Object.entries(interviews)
    .map(([id, iv]) => ({ a: personas[Number(id)], iv }))
    .filter((r): r is { a: Persona; iv: InterviewEvent } => !!r.a)
    .sort((x, y) => y.a.influence - x.a.influence), [interviews, personas])
  const n = rows.length
  if (!n) return <div className="text-muted text-sm text-center mt-10 px-6">Exit interviews start when the discussion ends: everyone is asked what they now conclude.</div>

  const count = (i: Intent) => rows.filter(r => r.iv.intent === i).length
  const prom = rows.filter(r => r.iv.recommend >= 9).length, det = rows.filter(r => r.iv.recommend <= 6).length
  const up = rows.filter(r => r.iv.changedMind === 'More positive').length, down = rows.filter(r => r.iv.changedMind === 'More negative').length
  const ql = q.trim().toLowerCase()
  const visible = rows.filter(r => (intent === 'all' || r.iv.intent === intent) && (group === 'all' || r.a.professionGroup === group)
    && (!ql || r.iv.quote.toLowerCase().includes(ql) || r.a.name.toLowerCase().includes(ql)))

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      <div className="card p-4 space-y-2">
        <div className="flex h-3 rounded-full overflow-hidden bg-panel-2">
          {(['Would buy/use', 'Maybe', 'Would not'] as Intent[]).map(i => <div key={i} style={{ width: `${(count(i) / n) * 100}%`, background: INTENT_COLOR[i] }} title={`${i}: ${count(i)}`} />)}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {(['Would buy/use', 'Maybe', 'Would not'] as Intent[]).map(i => <span key={i}><b style={{ color: INTENT_COLOR[i] }}>{Math.round((count(i) / n) * 100)}%</b> {i.toLowerCase()}</span>)}
          <span className="text-muted">·</span>
          <span title="Promoters (9-10) minus detractors (0-6)">NPS <b>{Math.round(((prom - det) / n) * 100)}</b></span>
          <span className="text-muted">· changed their mind: {up} up, {down} down · {n.toLocaleString()} interviewed</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select className="input input-sm" value={intent} onChange={e => { setIntent(e.target.value as 'all' | Intent); setLimit(TAKES_PAGE) }} aria-label="Intent">
          <option value="all">Everyone</option>
          <option value="Would buy/use">Would buy/use</option>
          <option value="Maybe">Maybe</option>
          <option value="Would not">Would not</option>
        </select>
        <select className="input input-sm" value={group} onChange={e => { setGroup(e.target.value); setLimit(TAKES_PAGE) }} aria-label="Profession group">
          <option value="all">All professions</option>
          {PROFESSION_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
        <div className="relative flex-1 min-w-[150px]">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
          <input className="input input-sm" style={{ width: '100%', paddingLeft: 24 }} placeholder="Search what they said" value={q} onChange={e => { setQ(e.target.value); setLimit(TAKES_PAGE) }} />
        </div>
        <span className="text-muted">{visible.length.toLocaleString()} shown · most influential first</span>
      </div>
      <div className="grid md:grid-cols-2 gap-2">
        {visible.slice(0, limit).map(({ a, iv }) => (
          <button key={a.id} onClick={() => onSelect(a.id)} className="card p-3 text-left cursor-pointer">
            <div className="flex items-center gap-1.5 text-xs min-w-0">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: hexToCss(GROUP_COLORS[a.professionGroup]) }} />
              <span className="font-semibold truncate">{a.name}</span>
              <span className="text-muted truncate">· {a.profession} · {a.region}</span>
            </div>
            <div className="text-sm mt-1 leading-snug">“{iv.quote}”</div>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5 text-[11px]">
              <span className="chip" style={{ borderColor: INTENT_COLOR[iv.intent], color: INTENT_COLOR[iv.intent] }}>{iv.intent}</span>
              <span className="text-muted">recommends {iv.recommend}/10</span>
              {iv.changedMind !== 'No' && <span className="text-muted">· changed mind: {iv.changedMind.toLowerCase()}</span>}
            </div>
          </button>
        ))}
      </div>
      {visible.length > limit && (
        <button className="btn btn-ghost w-full justify-center text-xs" onClick={() => setLimit(l => l + TAKES_PAGE)}>Show more ({(visible.length - limit).toLocaleString()} more)</button>
      )}
    </div>
  )
}

function Market() {
  const market = useStore(s => s.market)
  const marketPosition = useStore(s => s.scorecard?.marketPosition)
  const empty = (text: string) => <div className="text-muted text-sm text-center mt-10 px-6">{text}</div>
  if (!market) return empty('The market scan runs before first impressions.')
  if (market.status === 'off') return empty('The market scan was turned off for this run, so the agents judged it without knowing the alternatives.')
  if (market.status === 'unavailable' || !market.brief) return empty(`Market scan unavailable (${market.reason ?? 'unknown error'}), so the agents judged it without knowing the alternatives.`)
  const b = market.brief, ms = market.moodShifts
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
      <div className="card p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted uppercase tracking-wide">{b.category}</span>
          {market.status === 'simulated' && <span className="chip" style={{ borderColor: '#f5c242', color: '#f5c242' }}>simulated, not real market data</span>}
        </div>
        <p className="mt-1 leading-relaxed">{b.summary}</p>
        <div className="mt-2 text-xs text-muted">Price range: <b className="text-text">{b.priceRange}</b></div>
        {ms && (ms.wary || ms.excited) ? <div className="mt-1 text-xs text-muted">The news put {ms.wary ?? 0} agents in a wary mood and {ms.excited ?? 0} in an excited one.</div> : null}
        {marketPosition && <div className="mt-2 text-xs"><span className="text-muted">The report's take: </span>{marketPosition}</div>}
        <div className="mt-2 text-[11px] text-muted">Each agent only knew part of this, depending on their feeds and how early they adopt tech. About 30% of buyers and users already own an alternative.</div>
      </div>
      <div>
        <div className="text-xs text-muted uppercase tracking-wide mb-2 flex items-center gap-1.5"><Store size={12} /> Already on the market</div>
        <div className="grid sm:grid-cols-2 gap-2">
          {b.competitors.map(c => (
            <div key={c.name} className="card p-3">
              <div className="flex items-baseline gap-2 min-w-0">
                <span className="font-semibold truncate">{c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="hover:underline">{c.name}</a> : c.name}</span>
                <span className="text-xs text-muted truncate">{c.maker}</span>
                <span className="ml-auto font-semibold text-accent shrink-0">{c.price}</span>
              </div>
              <div className="text-xs mt-1">{c.pitch}</div>
              <div className="text-xs mt-1.5"><span className="text-pos">Liked for: </span>{c.likedFor}</div>
              <div className="text-xs"><span className="text-neg">Complaints: </span>{c.complaints}</div>
            </div>
          ))}
        </div>
      </div>
      {b.news.length > 0 && (
        <div>
          <div className="text-xs text-muted uppercase tracking-wide mb-2 flex items-center gap-1.5"><Newspaper size={12} /> In the news</div>
          <div className="space-y-2">
            {b.news.map(n => (
              <div key={n.headline} className="card p-3">
                <div className="flex items-start gap-2">
                  <div className="font-medium flex-1">{n.url ? <a href={n.url} target="_blank" rel="noreferrer" className="hover:underline">{n.headline}</a> : n.headline}</div>
                  <span className="chip shrink-0" style={{ borderColor: n.tone === 'positive' ? '#3ddc97' : n.tone === 'negative' ? '#ff6b6b' : undefined, color: n.tone === 'positive' ? '#3ddc97' : n.tone === 'negative' ? '#ff6b6b' : undefined }}>{n.tone}</span>
                </div>
                <div className="text-xs text-muted mt-0.5">{n.source} · {n.date}</div>
                <div className="text-xs mt-1">{n.gist}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {(b.buyerComplaints.length > 0 || b.substitutes.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-3">
          {b.buyerComplaints.length > 0 && <div><div className="text-xs text-muted uppercase tracking-wide mb-1.5">What buyers complain about</div><div className="flex flex-wrap gap-1.5">{b.buyerComplaints.map(x => <span key={x} className="chip">{x}</span>)}</div></div>}
          {b.substitutes.length > 0 && <div><div className="text-xs text-muted uppercase tracking-wide mb-1.5">What people do instead</div><div className="flex flex-wrap gap-1.5">{b.substitutes.map(x => <span key={x} className="chip">{x}</span>)}</div></div>}
        </div>
      )}
      {b.sources.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">Sources ({b.sources.length})</summary>
          <ul className="mt-1.5 space-y-0.5 pl-4 list-disc">{b.sources.map(s => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">{s.title || s.url}</a></li>)}</ul>
        </details>
      )}
    </div>
  )
}

function Feed({ onSelect }: { onSelect: (agentId: number) => void }) {
  const posts = useStore(s => s.posts)
  const postOrder = useStore(s => s.postOrder)
  const personas = useStore(s => s.personas)
  const totalRounds = useStore(s => s.totalRounds)
  const [sort, setSort] = useState<Sort>('latest')
  const [stance, setStance] = useState<Stance>('all')
  const [group, setGroup] = useState('all')
  const [round, setRound] = useState('all')
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)

  const threads = useMemo(() => {
    const byRoot = new Map<number, Thread>()
    const rootOf = (p: AppPost) => {
      let cur = p
      for (let hops = 0; cur.replyTo != null && posts[cur.replyTo] && hops < 50; hops++) cur = posts[cur.replyTo]
      return cur
    }
    for (const id of postOrder) {
      const p = posts[id]
      if (!p) continue
      const root = rootOf(p)
      let th = byRoot.get(root.id)
      if (!th) { th = { root, replies: [], last: root.t, engagement: 0 }; byRoot.set(root.id, th) }
      if (p.id !== root.id) th.replies.push(p)
      th.last = Math.max(th.last, p.t)
    }
    for (const th of byRoot.values()) {
      th.engagement = th.replies.length * 2 + [th.root, ...th.replies].reduce((a, p) => a + p.reposts * 1.5 + p.likes + p.mindsChanged * 3, 0)
    }
    return [...byRoot.values()]
  }, [posts, postOrder])

  const ql = q.trim().toLowerCase()
  const matches = useMemo(() => (p: AppPost) => !ql || p.text.toLowerCase().includes(ql) || (personas[p.agentId]?.name.toLowerCase().includes(ql) ?? false), [ql, personas])
  const visible = useMemo(() => {
    const out = threads.filter(th => {
      const a = personas[th.root.agentId]
      if (group !== 'all' && a?.professionGroup !== group) return false
      if (round !== 'all' && th.root.round !== Number(round)) return false
      if (!stanceOk(th.root.score, stance)) return false
      return matches(th.root) || th.replies.some(matches)
    })
    out.sort(sort === 'latest' ? (a, b) => b.last - a.last : (a, b) => b.engagement - a.engagement || b.last - a.last)
    return out
  }, [threads, personas, group, round, stance, matches, sort])

  return (
    <>
      <div className="px-4 py-2 border-b border-line flex flex-wrap items-center gap-2 text-xs">
        <div className="flex items-center rounded-lg border border-line overflow-hidden">
          {(['latest', 'top'] as Sort[]).map(s => (
            <button key={s} onClick={() => setSort(s)} className={`px-2.5 py-1 ${sort === s ? 'bg-panel-2 text-text' : 'text-muted hover:text-text'}`}>{s === 'latest' ? 'Latest' : 'Top'}</button>
          ))}
        </div>
        <select className="input input-sm" value={stance} onChange={e => { setStance(e.target.value as Stance); setLimit(PAGE) }} aria-label="Stance">
          <option value="all">All stances</option>
          <option value="for">For (6.5+)</option>
          <option value="undecided">Undecided</option>
          <option value="against">Against (under 4)</option>
        </select>
        <select className="input input-sm" value={group} onChange={e => { setGroup(e.target.value); setLimit(PAGE) }} aria-label="Profession group">
          <option value="all">All professions</option>
          {PROFESSION_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
        <select className="input input-sm" value={round} onChange={e => { setRound(e.target.value); setLimit(PAGE) }} aria-label="Round">
          <option value="all">All rounds</option>
          <option value="0">Opening posts</option>
          {Array.from({ length: totalRounds }, (_, i) => <option key={i + 1} value={i + 1}>Round {i + 1}</option>)}
        </select>
        <div className="relative flex-1 min-w-[150px]">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
          <input className="input input-sm" style={{ width: '100%', paddingLeft: 24 }} placeholder="Search posts or people" value={q} onChange={e => { setQ(e.target.value); setLimit(PAGE) }} />
        </div>
        <span className="text-muted">{visible.length.toLocaleString()} threads · {postOrder.length.toLocaleString()} posts</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {visible.length === 0 && (
          <div className="text-muted text-sm text-center mt-10">
            {postOrder.length ? 'No posts match these filters.' : 'Nobody has posted yet. The app opens after first impressions.'}
          </div>
        )}
        {visible.slice(0, limit).map(th => <ThreadView key={th.root.id} th={th} personas={personas} onSelect={onSelect} match={ql ? matches : null} />)}
        {visible.length > limit && (
          <button className="btn btn-ghost w-full justify-center text-xs" onClick={() => setLimit(l => l + PAGE)}>
            Show more ({(visible.length - limit).toLocaleString()} more threads)
          </button>
        )}
      </div>
    </>
  )
}

function ThreadView({ th, personas, onSelect, match }: { th: Thread; personas: Persona[]; onSelect: (id: number) => void; match: ((p: AppPost) => boolean) | null }) {
  const [open, setOpen] = useState(false)
  // While searching, surface the replies that match instead of the first two.
  const shown = open ? th.replies : match ? th.replies.filter(match).slice(0, 5) : th.replies.slice(0, 2)
  const hidden = th.replies.length - shown.length
  return (
    <div className="card p-3 fade-in">
      <PostCard p={th.root} a={personas[th.root.agentId]} parent={null} onSelect={onSelect} />
      {th.replies.length > 0 && (
        <div className="mt-2 ml-5 pl-3 border-l border-line space-y-2">
          {shown.map(r => (
            <PostCard key={r.id} p={r} a={personas[r.agentId]} onSelect={onSelect}
              parent={r.replyTo != null && r.replyTo !== th.root.id ? th.replies.find(x => x.id === r.replyTo) ?? null : null} personas={personas} small />
          ))}
          {(open || hidden > 0) && (
            <button className="text-xs text-accent hover:underline" onClick={() => setOpen(o => !o)}>
              {open ? 'Hide replies' : `Show ${hidden} more ${hidden === 1 ? 'reply' : 'replies'}`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const PostCard = memo(function PostCard({ p, a, parent, personas, onSelect, small }: {
  p: AppPost; a: Persona | undefined; parent: AppPost | null; personas?: Persona[]; onSelect: (id: number) => void; small?: boolean
}) {
  if (!a) return null
  const initials = a.name.split(' ').map(w => w[0]).slice(0, 2).join('')
  return (
    <div className="flex gap-2.5">
      <button onClick={() => onSelect(a.id)} title={`Open ${a.name}`}
        className={`${small ? 'w-7 h-7 text-[10px]' : 'w-9 h-9 text-xs'} shrink-0 rounded-full font-bold flex items-center justify-center text-[#0b0f17]`}
        style={{ background: hexToCss(GROUP_COLORS[a.professionGroup]) }}>{initials}</button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-xs min-w-0">
          <button className="font-semibold text-text hover:underline truncate" onClick={() => onSelect(a.id)}>{a.name}</button>
          <span className="text-muted truncate">· {a.profession} · {a.region} · {p.round === 0 ? 'opening post' : `round ${p.round}`}</span>
          <span className="ml-auto font-semibold shrink-0" style={{ color: col(p.score) }} title="Their score when they wrote this">{p.score.toFixed(1)}</span>
        </div>
        {parent && personas && <div className="text-[11px] text-muted">replying to {personas[parent.agentId]?.name.split(' ')[0]}</div>}
        <div className={`${small ? 'text-[13px]' : 'text-sm'} leading-snug mt-0.5`}>{p.text}</div>
        <div className="flex items-center gap-4 text-[11px] text-muted mt-1">
          <span className="flex items-center gap-1" title="Replies"><MessageSquare size={12} />{p.replyIds.length}</span>
          <span className="flex items-center gap-1" title="Reposts"><Repeat2 size={12} />{p.reposts}</span>
          <span className="flex items-center gap-1" title="Likes"><Heart size={12} />{p.likes}</span>
          {p.mindsChanged > 0 && <span className="flex items-center gap-1 text-text" title="People whose score this post changed"><Sparkles size={12} />changed {p.mindsChanged} {p.mindsChanged === 1 ? 'mind' : 'minds'}</span>}
        </div>
      </div>
    </div>
  )
})
