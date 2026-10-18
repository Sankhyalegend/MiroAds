import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Image, Globe, Tag, Lightbulb, Users, Play, Cpu, Database, Loader2 } from 'lucide-react'
import { useStore } from '../store'
import { api } from '../api'
import type { Stimulus, StimulusType } from '../types'

const TYPES: { id: StimulusType; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'creative', label: 'Image / creative', icon: <Image size={16} />, hint: 'Poster, ad, banner, packaging' },
  { id: 'website', label: 'Website', icon: <Globe size={16} />, hint: 'Landing page or product site' },
  { id: 'offer', label: 'Offer', icon: <Tag size={16} />, hint: 'Price, discount, bundle, promo' },
  { id: 'idea', label: 'Business idea', icon: <Lightbulb size={16} />, hint: 'Pitch, concept, one-pager' },
]

const SAMPLE: Record<StimulusType, { title: string; brief: string }> = {
  creative: {
    title: 'Nightshift launch poster',
    brief: 'Poster shows a dim home office at night, a desk lamp glowing amber over a closed laptop. Tagline: "Your light knows when to stop." Small text: Nightshift smart desk lamp, $149, shifts colour temperature with your calendar. Early-bird $30 off for first 500.',
  },
  website: {
    title: 'Nightshift landing page',
    brief: 'Hero: "Light that follows your day." Subhead about calendar-linked colour temperature. Three feature cards, a demo video, pricing at $149 two scrolls down, email signup form with 5 fields, no reviews yet, footer with warranty note.',
  },
  offer: {
    title: 'Nightshift early-bird offer',
    brief: 'Early-bird: $119 instead of $149 for the first 500 units, ends 7 November. Includes 2-year warranty. No subscription. Ships in December.',
  },
  idea: {
    title: 'Synthetic focus groups for marketers',
    brief: 'A tool where marketers upload a creative or offer and a crowd of AI personas with different jobs, incomes and ideologies react, argue, and produce a scorecard: objections, missing KPIs, and better variants. $49 per run or $299/month. Target: growth teams at 20-200 person startups.',
  },
}

const HAIKU_IN = 0.10 / 1e6, HAIKU_OUT = 0.50 / 1e6, SONNET_IN = 2 / 1e6, SONNET_OUT = 10 / 1e6
function estimate(crowd: number, rounds: number, devMode: boolean) {
  const stage1 = crowd * (2600 * HAIKU_IN + 260 * HAIKU_OUT)
  const social = crowd * 0.15 * rounds * (3400 * HAIKU_IN + 160 * HAIKU_OUT)
  const analysts = devMode ? 12 * (6000 * HAIKU_IN + 900 * HAIKU_OUT) : 9 * (6000 * SONNET_IN + 900 * SONNET_OUT) + 1 * (12000 * SONNET_IN + 2000 * SONNET_OUT)
  return stage1 + social + analysts
}

export default function Upload() {
  const nav = useNavigate()
  const { setStimulus, crowdSize, setCrowdSize, rounds, setRounds, start, engine, setEngine, health, checkBackend } = useStore()
  const [type, setType] = useState<StimulusType>('creative')
  const [title, setTitle] = useState(SAMPLE.creative.title)
  const [brief, setBrief] = useState(SAMPLE.creative.brief)
  const [url, setUrl] = useState('')
  const [imageUrl, setImageUrl] = useState<string | undefined>()
  const [offer, setOffer] = useState({ product: 'Nightshift smart desk lamp', price: '$149', discount: '$30 off first 500 units', urgency: 'Ends 7 November', terms: '2-year warranty, no subscription' })
  const [audience, setAudience] = useState('Remote software developers 25-40, students, productivity enthusiasts; plus a general-public control sample')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [libN, setLibN] = useState(2000)
  const [libJob, setLibJob] = useState<{ running: boolean; done: number; total: number; cost: number; error: string | null } | null>(null)

  useEffect(() => { checkBackend() }, [checkBackend])
  useEffect(() => {
    if (!libJob?.running) return
    const t = window.setInterval(async () => {
      try { const s = await api.libraryStats(); setLibJob(s.job); if (!s.job.running) { clearInterval(t); checkBackend() } } catch { clearInterval(t) }
    }, 1500)
    return () => clearInterval(t)
  }, [libJob?.running, checkBackend])

  const pickType = (t: StimulusType) => { setType(t); setTitle(SAMPLE[t].title); setBrief(SAMPLE[t].brief) }
  const onFile = (f: File | undefined) => {
    if (!f) return
    const r = new FileReader(); r.onload = () => setImageUrl(String(r.result)); r.readAsDataURL(f)
    if (!title) setTitle(f.name)
  }

  const go = async () => {
    setErr(null); setBusy(true)
    const s: Stimulus = {
      type, title: title || 'Untitled', targetAudience: audience,
      brief: type === 'offer' ? `${offer.product}. Price ${offer.price}. ${offer.discount}. ${offer.urgency}. Terms: ${offer.terms}. ${brief}` : type === 'website' ? `Website ${url}. ${brief}` : brief,
      imageUrl, url: url || undefined, offer: type === 'offer' ? offer : undefined,
    }
    setStimulus(s)
    const id = await start()
    setBusy(false)
    if (!id) { setErr(useStore.getState().error ?? 'Could not start run'); return }
    nav(id === 'mock' ? '/run' : `/run/${id}`)
  }

  const buildLibrary = async () => {
    setErr(null)
    try {
      await api.buildLibrary(libN, health?.provider === 'fake' ? 1 : 6)
      setLibJob({ running: true, done: 0, total: libN, cost: 0, error: null })
    } catch (e) { setErr((e as Error).message) }
  }

  const liveOk = !!health && health.library > 0
  const est = estimate(crowdSize, rounds, health?.devMode ?? true)
  const providerLabel = health ? (health.provider === 'fake' ? 'fake provider (no API key, $0)' : `${health.crowdModel}${health.devMode ? ' + dev-mode analysts' : ` + ${health.analystModel}`}`) : 'backend offline'

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">What should the crowd judge?</h1>
        <p className="text-muted mt-1">Upload a stimulus. A crowd sampled from a library of simulated people with different jobs, incomes, countries, ideologies and personalities will react, argue, and a research team will write it up.</p>
      </div>

      <div className="grid md:grid-cols-[1fr_340px] gap-5">
        <div className="card p-5 space-y-5">
          <div className="flex flex-wrap gap-2">
            {TYPES.map(t => (
              <button key={t.id} className="tab flex items-center gap-2" data-active={type === t.id} onClick={() => pickType(t.id)} title={t.hint}>{t.icon}{t.label}</button>
            ))}
          </div>
          <div><label className="text-xs text-muted">Title</label><input className="input mt-1" value={title} onChange={e => setTitle(e.target.value)} /></div>
          {type === 'creative' && (
            <div>
              <label className="text-xs text-muted">Image (live engine describes it with a vision model; the description is what agents read)</label>
              <div className="mt-1 flex gap-3 items-start">
                <label className="btn btn-ghost cursor-pointer"><Image size={16} /> Choose image<input type="file" accept="image/*" className="hidden" onChange={e => onFile(e.target.files?.[0])} /></label>
                {imageUrl && <img src={imageUrl} alt="" className="h-24 rounded-lg border border-line object-cover" />}
              </div>
            </div>
          )}
          {type === 'website' && <div><label className="text-xs text-muted">URL</label><input className="input mt-1" placeholder="https://" value={url} onChange={e => setUrl(e.target.value)} /></div>}
          {type === 'offer' && (
            <div className="grid grid-cols-2 gap-3">
              {(['product', 'price', 'discount', 'urgency', 'terms'] as const).map(k => (
                <div key={k} className={k === 'terms' ? 'col-span-2' : ''}><label className="text-xs text-muted capitalize">{k}</label><input className="input mt-1" value={offer[k]} onChange={e => setOffer({ ...offer, [k]: e.target.value })} /></div>
              ))}
            </div>
          )}
          <div><label className="text-xs text-muted">{type === 'idea' ? 'Describe the idea' : 'Describe what the crowd sees'}</label><textarea className="input mt-1 min-h-[140px]" value={brief} onChange={e => setBrief(e.target.value)} /></div>
          <div><label className="text-xs text-muted">Target audience (the sample is weighted toward this, with contrarian and outsider quotas)</label><input className="input mt-1" value={audience} onChange={e => setAudience(e.target.value)} /></div>
        </div>

        <div className="space-y-4">
          <div className="card p-4 space-y-3">
            <div className="flex items-center gap-2 font-semibold"><Cpu size={16} /> Engine</div>
            <div className="flex gap-2">
              <button className="tab flex-1" data-active={engine === 'live'} onClick={() => setEngine('live')}>Live (LLM)</button>
              <button className="tab flex-1" data-active={engine === 'mock'} onClick={() => setEngine('mock')}>Mock (browser)</button>
            </div>
            {engine === 'live' && (
              <div className="text-xs space-y-2">
                <div className={health ? 'text-muted' : 'text-neg'}>{providerLabel}</div>
                {health && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted flex items-center gap-1"><Database size={12} /> Library: <b className="text-text">{health.library.toLocaleString()}</b> personas</span>
                    {!libJob?.running && <button className="btn btn-ghost text-xs py-1" onClick={buildLibrary}>Build {libN.toLocaleString()}</button>}
                  </div>
                )}
                {health && !libJob?.running && (
                  <input type="range" min={500} max={10000} step={500} value={libN} onChange={e => setLibN(Number(e.target.value))} className="w-full accent-[#7c9cff]" title="How many personas to generate" />
                )}
                {libJob?.running && <div className="flex items-center gap-2 text-muted"><Loader2 size={12} className="animate-spin" /> generating {libJob.done.toLocaleString()} / {libJob.total.toLocaleString()} · ${libJob.cost.toFixed(2)}</div>}
                {libJob?.error && <div className="text-neg">{libJob.error}</div>}
                {health && health.library === 0 && <div className="text-neu">Build the persona library first (one-time, about $3 for 10,000 on Haiku 5.5).</div>}
                {!health && <button className="btn btn-ghost text-xs py-1" onClick={() => checkBackend()}>Retry connection</button>}
              </div>
            )}
          </div>

          <div className="card p-4 space-y-4">
            <div className="flex items-center gap-2 font-semibold"><Users size={16} /> Crowd</div>
            <div>
              <div className="flex justify-between text-sm"><span className="text-muted">Size</span><span className="font-semibold">{crowdSize.toLocaleString()} agents</span></div>
              <input type="range" min={50} max={engine === 'live' ? 1500 : 3000} step={50} value={crowdSize} onChange={e => setCrowdSize(Number(e.target.value))} className="w-full mt-2 accent-[#7c9cff]" />
            </div>
            <div>
              <div className="flex justify-between text-sm"><span className="text-muted">Social rounds</span><span className="font-semibold">{rounds}</span></div>
              <input type="range" min={0} max={10} value={rounds} onChange={e => setRounds(Number(e.target.value))} className="w-full mt-2 accent-[#7c9cff]" />
            </div>
            <div className="text-xs text-muted">
              {engine === 'live' && health?.provider !== 'fake' ? <>Estimated cost: <b className="text-text">${est.toFixed(2)}</b> · run budget cap ${health?.runBudgetUsd ?? 2}</> : 'No API cost with the mock or fake provider.'}
            </div>
          </div>

          <button className="btn w-full justify-center text-base py-3" onClick={go} disabled={busy || (engine === 'live' && !liveOk)}>
            {busy ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />} Run the crowd
          </button>
          {err && <div className="text-xs text-neg">{err}</div>}
        </div>
      </div>
    </div>
  )
}
