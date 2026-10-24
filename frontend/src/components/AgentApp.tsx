import { memo, useMemo, useState } from 'react'
import { MessageSquare, Repeat2, Heart, Sparkles, Search } from 'lucide-react'
import { useStore, type AppPost } from '../store'
import { GROUP_COLORS, PROFESSION_GROUPS, hexToCss } from '../mock/personas'
import type { Persona } from '../types'

const col = (s: number) => s >= 6.5 ? '#3ddc97' : s >= 4 ? '#f5c242' : '#ff6b6b'
const PAGE = 30

type Sort = 'latest' | 'top'
type Stance = 'all' | 'for' | 'undecided' | 'against'
interface Thread { root: AppPost; replies: AppPost[]; last: number; engagement: number }

const stanceOk = (s: number, st: Stance) => st === 'all' || (st === 'for' ? s >= 6.5 : st === 'against' ? s < 4 : s >= 4 && s < 6.5)

/** The social app the agents use during the discussion: threads, reposts, likes, and who changed whose mind. */
export default function AgentApp({ onSelect }: { onSelect: (agentId: number) => void }) {
  return (
    <div className="h-full flex flex-col min-h-0">
      <Feed onSelect={onSelect} />
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
  const visible = useMemo(() => {
    const matches = (p: AppPost) => !ql || p.text.toLowerCase().includes(ql) || (personas[p.agentId]?.name.toLowerCase().includes(ql) ?? false)
    const out = threads.filter(th => {
      const a = personas[th.root.agentId]
      if (group !== 'all' && a?.professionGroup !== group) return false
      if (round !== 'all' && th.root.round !== Number(round)) return false
      if (!stanceOk(th.root.score, stance)) return false
      return matches(th.root) || th.replies.some(matches)
    })
    out.sort(sort === 'latest' ? (a, b) => b.last - a.last : (a, b) => b.engagement - a.engagement || b.last - a.last)
    return out
  }, [threads, personas, group, round, stance, ql, sort])

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
        {visible.slice(0, limit).map(th => <ThreadView key={th.root.id} th={th} personas={personas} onSelect={onSelect} />)}
        {visible.length > limit && (
          <button className="btn btn-ghost w-full justify-center text-xs" onClick={() => setLimit(l => l + PAGE)}>
            Show more ({(visible.length - limit).toLocaleString()} more threads)
          </button>
        )}
      </div>
    </>
  )
}

function ThreadView({ th, personas, onSelect }: { th: Thread; personas: Persona[]; onSelect: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const shown = open ? th.replies : th.replies.slice(0, 2)
  return (
    <div className="card p-3 fade-in">
      <PostCard p={th.root} a={personas[th.root.agentId]} parent={null} onSelect={onSelect} />
      {th.replies.length > 0 && (
        <div className="mt-2 ml-5 pl-3 border-l border-line space-y-2">
          {shown.map(r => (
            <PostCard key={r.id} p={r} a={personas[r.agentId]} onSelect={onSelect}
              parent={r.replyTo != null && r.replyTo !== th.root.id ? th.replies.find(x => x.id === r.replyTo) ?? null : null} personas={personas} small />
          ))}
          {th.replies.length > 2 && (
            <button className="text-xs text-accent hover:underline" onClick={() => setOpen(o => !o)}>
              {open ? 'Hide replies' : `Show ${th.replies.length - 2} more ${th.replies.length - 2 === 1 ? 'reply' : 'replies'}`}
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
