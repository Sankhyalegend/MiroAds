import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Image, Globe, Tag, Lightbulb, Play, Database, Loader2, UploadCloud, FileText, File as FileIcon, X, Wand2, Settings2, Store } from 'lucide-react'
import { useStore } from '../store'
import { api } from '../api'
import type { Attachment, Stimulus, StimulusType } from '../types'

const TYPES: { id: StimulusType; label: string; icon: React.ReactNode; hint: string; placeholder: string }[] = [
  { id: 'creative', label: 'Ad or poster', icon: <Image size={18} />, hint: 'Poster, ad, banner, packaging', placeholder: 'Describe what people see: the picture, the headline, the small print, the price…' },
  { id: 'website', label: 'Website', icon: <Globe size={18} />, hint: 'Landing page or product site', placeholder: 'Describe the page from top to bottom: headline, what it offers, price, sign-up…' },
  { id: 'offer', label: 'Offer', icon: <Tag size={18} />, hint: 'Price, discount, bundle, promo', placeholder: 'Anything else people should know about the offer' },
  { id: 'idea', label: 'Business idea', icon: <Lightbulb size={18} />, hint: 'Pitch, concept, one-pager', placeholder: 'Pitch it in a few sentences: the problem, the product, who pays and how much' },
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
const SAMPLE_AUDIENCE = 'Remote software developers 25-40, students, productivity enthusiasts; plus a general-public control sample'
const SAMPLE_OFFER = { product: 'Nightshift smart desk lamp', price: '$149', discount: '$30 off first 500 units', urgency: 'Ends 7 November', terms: '2-year warranty, no subscription' }
const AUDIENCES = ['Remote developers 25-40', 'Students', 'Small business owners', 'Parents with young kids', 'Designers', 'General public']

const SIZES = [{ n: 50, label: 'Quick' }, { n: 100, label: 'Standard' }, { n: 300, label: 'Deep' }, { n: 1000, label: 'Large' }]
const ROUND_CHOICES = [{ n: 3, label: 'Short' }, { n: 5, label: 'Normal' }, { n: 8, label: 'Long' }]

// ---- files ----
const MB = 1024 * 1024
const MAX_FILES = 6
const LIMIT = { image: 5 * MB, pdf: 10 * MB, text: 1 * MB }
const ACCEPT = 'image/png,image/jpeg,image/webp,image/gif,application/pdf,.pdf,.txt,.md,.csv,.json'
type Kind = keyof typeof LIMIT
function kindOf(f: File): Kind | null {
  if (/^image\/(png|jpe?g|webp|gif)$/.test(f.type)) return 'image'
  if (f.type === 'application/pdf' || /\.pdf$/i.test(f.name)) return 'pdf'
  if (f.type.startsWith('text/') || /\.(txt|md|csv|json)$/i.test(f.name)) return 'text'
  return null
}
const fmtSize = (b: number) => b >= MB ? `${(b / MB).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`
function readFile(f: File, kind: Kind): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onerror = () => reject(new Error(`Couldn't read ${f.name}`))
    r.onload = () => resolve(kind === 'text'
      ? { name: f.name, type: f.type || 'text/plain', size: f.size, text: String(r.result) }
      : { name: f.name, type: kind === 'pdf' ? 'application/pdf' : f.type, size: f.size, data: String(r.result) })
    if (kind === 'text') r.readAsText(f); else r.readAsDataURL(f)
  })
}

// ---- cost and time ----
const HAIKU_IN = 0.10 / 1e6, HAIKU_OUT = 0.50 / 1e6, SONNET_IN = 2 / 1e6, SONNET_OUT = 10 / 1e6, SEARCH = 0.01
function estimate(crowd: number, rounds: number, devMode: boolean, marketScan: boolean) {
  const stage1 = crowd * (2750 * HAIKU_IN + 260 * HAIKU_OUT)
  // Everyone opens the app at least once, on top of the activity-weighted turns each round.
  const social = crowd * (0.15 * rounds + (rounds > 0 ? 0.4 : 0)) * (3550 * HAIKU_IN + 160 * HAIKU_OUT)
  const interviews = crowd * (1300 * HAIKU_IN + 250 * HAIKU_OUT)
  const analysts = devMode ? 13 * (6500 * HAIKU_IN + 900 * HAIKU_OUT) : 10 * (6500 * SONNET_IN + 900 * SONNET_OUT) + 1 * (13000 * SONNET_IN + 2000 * SONNET_OUT)
  // Research reads every search result (~120K tokens) on Haiku; the extraction runs on the analyst model.
  const market = marketScan ? 8 * SEARCH + 125000 * HAIKU_IN + 17000 * HAIKU_OUT + (devMode ? 6000 * HAIKU_IN + 2500 * HAIKU_OUT : 6000 * SONNET_IN + 2500 * SONNET_OUT) : 0
  return stage1 + social + interviews + analysts + market
}
/** Rough wall-clock minutes, from measured runs (100 agents, 5 rounds, market scan: about 2.3 minutes). */
const minutes = (crowd: number, rounds: number, marketScan: boolean) => Math.max(1, Math.round(((marketScan ? 60 : 0) + 20 + crowd * 0.25 + rounds * 8) / 60))

export default function Upload() {
  const nav = useNavigate()
  const { setStimulus, crowdSize, setCrowdSize, rounds, setRounds, start, engine, setEngine, health, checkBackend, marketScan, setMarketScan } = useStore()
  const [type, setType] = useState<StimulusType>('creative')
  const [title, setTitle] = useState('')
  const [brief, setBrief] = useState('')
  const [url, setUrl] = useState('')
  const [offer, setOffer] = useState({ product: '', price: '', discount: '', urgency: '', terms: '' })
  const [audience, setAudience] = useState('')
  const [competitors, setCompetitors] = useState('')
  const [files, setFiles] = useState<Attachment[]>([])
  const [fileErr, setFileErr] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
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
  useEffect(() => {
    if (!confirming) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setConfirming(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [confirming])

  // Switching type only swaps in that type's example if the form still holds an example (or nothing).
  const untouched = (!title && !brief) || Object.values(SAMPLE).some(s => s.title === title && s.brief === brief)
  const pickType = (t: StimulusType) => { setType(t); if (untouched && title) { setTitle(SAMPLE[t].title); setBrief(SAMPLE[t].brief) } }
  const loadExample = () => {
    setTitle(SAMPLE[type].title); setBrief(SAMPLE[type].brief); setAudience(SAMPLE_AUDIENCE)
    if (type === 'offer') setOffer(SAMPLE_OFFER)
    if (type === 'website' && !url) setUrl('https://nightshift.example')
  }

  const addFiles = async (list: FileList | File[]) => {
    setFileErr(null)
    const problems: string[] = []
    const next = [...files]
    for (const f of Array.from(list)) {
      const kind = kindOf(f)
      if (!kind) { problems.push(`${f.name}: use an image, a PDF or a text file`); continue }
      if (f.size > LIMIT[kind]) { problems.push(`${f.name} is too big (max ${fmtSize(LIMIT[kind])})`); continue }
      if (next.length >= MAX_FILES) { problems.push(`up to ${MAX_FILES} files`); break }
      if (next.some(x => x.name === f.name && x.size === f.size)) continue
      try { next.push(await readFile(f, kind)) } catch (e) { problems.push((e as Error).message) }
    }
    setFiles(next)
    if (problems.length) setFileErr(problems.join(' · '))
  }

  const go = async () => {
    setErr(null); setBusy(true)
    const s: Stimulus = {
      type, title: title.trim() || 'Untitled', targetAudience: audience,
      brief: type === 'offer' ? `${offer.product}. Price ${offer.price}. ${offer.discount}. ${offer.urgency}. Terms: ${offer.terms}. ${brief}` : type === 'website' ? `Website ${url}. ${brief}` : brief,
      url: url || undefined, offer: type === 'offer' ? offer : undefined, competitors: competitors.trim() || undefined,
      attachments: files.length ? files : undefined,
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
  const devMode = health?.devMode ?? true
  const est = estimate(crowdSize, rounds, devMode, marketScan)
  // Live runs with a real key cost money, so they are confirmed first with the size and the estimate.
  const paid = engine === 'live' && !!health && health.provider !== 'fake'
  const hasContent = !!brief.trim() || files.length > 0 || (type === 'website' && !!url.trim()) || (type === 'offer' && !!offer.product.trim())
  const blocker = !title.trim() ? 'Give it a title first.'
    : !hasContent ? 'Describe it or add a file first.'
    : engine === 'live' && !health ? 'The backend is offline. Start it, or switch to Demo.'
    : engine === 'live' && !liveOk ? 'Build the persona library first (under Advanced).'
    : null
  const typeInfo = TYPES.find(t => t.id === type)!

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 fade-in">
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[260px]">
          <h1 className="text-3xl font-bold tracking-tight">Test it on a crowd before you spend</h1>
          <p className="text-muted mt-1">Show an ad, a website, an offer or an idea to a crowd of simulated people with different jobs, incomes, countries and tastes. They react, argue in a social app, and a research team writes up what to fix.</p>
        </div>
        <button className="btn btn-ghost text-sm" onClick={loadExample}><Wand2 size={15} /> Try an example</button>
      </div>

      <div className="grid lg:grid-cols-[1fr_360px] gap-5 items-start">
        <div className="space-y-5 min-w-0">
          <Section n={1} title="What are you testing?" hint="Pick the kind of thing, give it a name, and describe it or add files.">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {TYPES.map(t => (
                <button key={t.id} onClick={() => pickType(t.id)}
                  className={`rounded-xl border p-3 text-left transition-colors ${type === t.id ? 'border-accent bg-accent/10' : 'border-line hover:border-accent/50'}`}>
                  <div className={type === t.id ? 'text-accent' : 'text-muted'}>{t.icon}</div>
                  <div className="font-medium text-sm mt-1.5">{t.label}</div>
                  <div className="text-[11px] text-muted leading-snug">{t.hint}</div>
                </button>
              ))}
            </div>
            <Field label="Name">
              <input className="input" value={title} onChange={e => setTitle(e.target.value)} placeholder={`e.g. ${SAMPLE[type].title}`} />
            </Field>
            {type === 'website' && (
              <Field label="Website address">
                <input className="input" placeholder="https://" value={url} onChange={e => setUrl(e.target.value)} />
              </Field>
            )}
            {type === 'offer' && (
              <div className="grid sm:grid-cols-2 gap-3">
                {(['product', 'price', 'discount', 'urgency', 'terms'] as const).map(k => (
                  <Field key={k} label={{ product: 'Product', price: 'Price', discount: 'Discount', urgency: 'Deadline or urgency', terms: 'Terms' }[k]} wide={k === 'terms'}>
                    <input className="input" value={offer[k]} placeholder={SAMPLE_OFFER[k]} onChange={e => setOffer({ ...offer, [k]: e.target.value })} />
                  </Field>
                ))}
              </div>
            )}

            <Field label="Files" note="optional">
              <div
                role="button" tabIndex={0} aria-label="Add files"
                onClick={() => fileInput.current?.click()}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.current?.click() } }}
                onDragOver={e => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }}
                className={`rounded-xl border-2 border-dashed px-4 py-6 text-center cursor-pointer transition-colors ${dragging ? 'border-accent bg-accent/10' : 'border-line hover:border-accent/60 hover:bg-panel-2/50'}`}>
                <UploadCloud size={26} className="mx-auto text-accent" />
                <div className="mt-2 font-medium text-sm">Drop files here, or <span className="text-accent underline underline-offset-2">browse</span></div>
                <div className="text-xs text-muted mt-1">Posters and screenshots, PDFs like a pitch deck or one-pager, or notes (.txt, .md). Up to {MAX_FILES} files: images 5 MB, PDFs 10 MB.</div>
                <input ref={fileInput} type="file" multiple accept={ACCEPT} className="hidden" onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }} />
              </div>
              {files.length > 0 && (
                <div className="grid sm:grid-cols-2 gap-2 mt-2">
                  {files.map((f, i) => (
                    <div key={f.name + i} className="flex items-center gap-3 rounded-lg bg-panel-2 border border-line p-2 fade-in">
                      {f.data && f.type.startsWith('image/')
                        ? <img src={f.data} alt="" className="w-11 h-11 rounded-md object-cover shrink-0" />
                        : <div className="w-11 h-11 rounded-md bg-panel grid place-items-center text-muted shrink-0">{f.type === 'application/pdf' ? <FileText size={18} /> : <FileIcon size={18} />}</div>}
                      <div className="min-w-0 flex-1">
                        <div className="text-sm truncate" title={f.name}>{f.name}</div>
                        <div className="text-[11px] text-muted">{f.type === 'application/pdf' ? 'PDF' : f.type.startsWith('image/') ? 'Image' : 'Note'} · {fmtSize(f.size)}</div>
                      </div>
                      <button aria-label={`Remove ${f.name}`} title="Remove" className="p-1.5 rounded-md text-muted hover:text-text hover:bg-panel" onClick={() => setFiles(files.filter((_, j) => j !== i))}><X size={14} /></button>
                    </div>
                  ))}
                </div>
              )}
              {fileErr && <div className="text-xs text-neg mt-1.5">{fileErr}</div>}
              {files.length > 0 && <div className="text-[11px] text-muted mt-1.5">{engine === 'live' ? 'The AI reads each file and the crowd sees a description of it, together with your text. You can check it later under "What the crowd saw".' : "The demo engine doesn't read files. Switch to Live AI to have them read."}</div>}
            </Field>

            <Field label={type === 'idea' ? 'Describe the idea' : 'Describe it'} note={files.length ? 'optional with files' : undefined}>
              <textarea className="input min-h-[130px]" value={brief} onChange={e => setBrief(e.target.value)} placeholder={typeInfo.placeholder} />
            </Field>
          </Section>

          <Section n={2} title="Who is it for?" hint="The crowd leans toward this audience, and always includes some sceptics and outsiders for contrast.">
            <Field label="Target audience">
              <input className="input" value={audience} onChange={e => setAudience(e.target.value)} placeholder="e.g. Remote software developers 25-40 in the US and India" />
              <div className="flex flex-wrap gap-1.5 mt-2">
                {AUDIENCES.map(a => (
                  <button key={a} className="chip hover:border-accent hover:text-text" onClick={() => setAudience(audience.trim() ? `${audience.trim().replace(/[,;]$/, '')}, ${a.toLowerCase()}` : a)}>+ {a}</button>
                ))}
              </div>
            </Field>
            <Field label="Competitors you already know about" note="optional, helps the market scan">
              <input className="input" placeholder="e.g. BenQ ScreenBar, Philips Hue, a $12 timer plug" value={competitors} onChange={e => setCompetitors(e.target.value)} />
            </Field>
          </Section>
        </div>

        <aside className="lg:sticky lg:top-[72px] space-y-4">
          <Section n={3} title="Run the test">
            <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-panel-2 text-sm">
              {(['live', 'mock'] as const).map(e => (
                <button key={e} onClick={() => setEngine(e)} className={`rounded-lg py-2 ${engine === e ? 'bg-panel text-text shadow' : 'text-muted hover:text-text'}`}>
                  {e === 'live' ? 'Live AI' : 'Demo (free)'}
                </button>
              ))}
            </div>
            <div className="text-xs flex items-center gap-2">
              {engine === 'live'
                ? <><span className={`w-2 h-2 rounded-full ${health ? 'bg-pos' : 'bg-neg'}`} /><span className="text-muted">{health ? (health.provider === 'fake' ? 'Connected · fake provider (no API key, $0)' : `Connected · ${health.crowdModel}${health.devMode ? ' · dev mode' : ` + ${health.analystModel}`} · ${health.library.toLocaleString()} people`) : 'Backend offline'}</span>
                  {!health && <button className="ml-auto text-accent hover:underline" onClick={() => checkBackend()}>Retry</button>}</>
                : <span className="text-muted">Simulated in your browser from the persona traits. No AI, no cost.</span>}
            </div>

            <div>
              <div className="text-xs text-muted mb-1.5">Crowd size</div>
              <div className="grid grid-cols-2 gap-2">
                {SIZES.map(s => (
                  <button key={s.n} onClick={() => setCrowdSize(s.n)}
                    className={`rounded-xl border p-2.5 text-left transition-colors ${crowdSize === s.n ? 'border-accent bg-accent/10' : 'border-line hover:border-accent/50'}`}>
                    <div className="text-sm font-medium">{s.label}</div>
                    <div className="text-[11px] text-muted">{s.n.toLocaleString()} people{paid ? ` · ~$${estimate(s.n, rounds, devMode, marketScan).toFixed(2)}` : ''}</div>
                  </button>
                ))}
              </div>
              {!SIZES.some(s => s.n === crowdSize) && <div className="text-[11px] text-muted mt-1.5">Custom: {crowdSize.toLocaleString()} people (Advanced)</div>}
            </div>

            <div>
              <div className="text-xs text-muted mb-1.5">Discussion length</div>
              <div className="grid grid-cols-3 gap-1 p-1 rounded-xl bg-panel-2 text-sm">
                {ROUND_CHOICES.map(r => (
                  <button key={r.n} onClick={() => setRounds(r.n)} className={`rounded-lg py-1.5 ${rounds === r.n ? 'bg-panel text-text shadow' : 'text-muted hover:text-text'}`}>
                    {r.label} <span className="text-[11px] text-muted">{r.n}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Store size={16} className="text-accent mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="text-sm font-medium">Scan the market first</div>
                <div className="text-[11px] text-muted leading-snug">Looks up competitors, prices and news on the web. Each person only knows what someone like them would have come across{paid ? ' (about $0.10)' : ''}.</div>
              </div>
              <button role="switch" aria-checked={marketScan} aria-label="Scan the market first" onClick={() => setMarketScan(!marketScan)}
                className={`w-10 h-6 rounded-full relative shrink-0 transition-colors ${marketScan ? 'bg-accent' : 'bg-line'}`}>
                <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${marketScan ? 'left-[18px]' : 'left-0.5'}`} />
              </button>
            </div>

            <div className="rounded-xl bg-panel-2 p-3 grid grid-cols-2 text-center">
              <div><div className="text-xl font-bold">{paid ? `$${est.toFixed(2)}` : 'Free'}</div><div className="text-[11px] text-muted">estimated cost</div></div>
              <div><div className="text-xl font-bold">{engine === 'live' ? `~${minutes(crowdSize, rounds, marketScan)} min` : '<1 min'}</div><div className="text-[11px] text-muted">until the report</div></div>
            </div>

            <button className="btn w-full justify-center text-base py-3" onClick={() => paid ? setConfirming(true) : go()} disabled={busy || !!blocker}>
              {busy ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />} {busy ? 'Starting…' : 'Run the test'}
            </button>
            {blocker && <div className="text-xs text-muted text-center -mt-1">{blocker}</div>}
            {paid && !blocker && <div className="text-[11px] text-muted text-center -mt-1">You'll confirm the cost before anything is spent. Stops at ${health?.runBudgetUsd ?? 2}.</div>}
            {err && <div className="text-xs text-neg">{err}</div>}
          </Section>

          <details className="card p-4 group">
            <summary className="cursor-pointer text-sm font-medium flex items-center gap-2 list-none"><Settings2 size={15} className="text-muted" /> Advanced <span className="text-[11px] text-muted font-normal">custom size, rounds, persona library</span></summary>
            <div className="space-y-4 mt-4">
              <div>
                <div className="flex justify-between text-sm"><span className="text-muted">Crowd size</span><span className="font-semibold">{crowdSize.toLocaleString()} people</span></div>
                <input type="range" min={50} max={engine === 'live' ? 1500 : 3000} step={50} value={crowdSize} onChange={e => setCrowdSize(Number(e.target.value))} className="w-full mt-2 accent-[#7c9cff]" aria-label="Crowd size" />
              </div>
              <div>
                <div className="flex justify-between text-sm"><span className="text-muted">Discussion rounds</span><span className="font-semibold">{rounds}</span></div>
                <input type="range" min={0} max={10} value={rounds} onChange={e => setRounds(Number(e.target.value))} className="w-full mt-2 accent-[#7c9cff]" aria-label="Discussion rounds" />
              </div>
              {engine === 'live' && health && (
                <div className="text-xs space-y-2 border-t border-line pt-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted flex items-center gap-1"><Database size={12} /> Persona library: <b className="text-text">{health.library.toLocaleString()}</b> people</span>
                    {!libJob?.running && <button className="btn btn-ghost text-xs py-1" onClick={buildLibrary}>Add {libN.toLocaleString()}</button>}
                  </div>
                  {!libJob?.running && <input type="range" min={500} max={10000} step={500} value={libN} onChange={e => setLibN(Number(e.target.value))} className="w-full accent-[#7c9cff]" aria-label="How many personas to generate" />}
                  {libJob?.running && <div className="flex items-center gap-2 text-muted"><Loader2 size={12} className="animate-spin" /> generating {libJob.done.toLocaleString()} / {libJob.total.toLocaleString()} · ${libJob.cost.toFixed(2)}</div>}
                  {libJob?.error && <div className="text-neg">{libJob.error}</div>}
                  {health.library === 0 && <div className="text-neu">Build the persona library first (one-time, about $3 for 10,000 on Haiku 5.5).</div>}
                </div>
              )}
            </div>
          </details>
        </aside>
      </div>

      {confirming && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setConfirming(false)}>
          <div className="card p-5 max-w-sm w-full space-y-3" role="dialog" aria-modal="true" aria-labelledby="confirm-title" onClick={e => e.stopPropagation()}>
            <h2 id="confirm-title" className="font-semibold text-lg">Start a paid run?</h2>
            <div className="text-sm space-y-1">
              <div><span className="text-muted">Crowd: </span><b>{crowdSize.toLocaleString()} people</b> · {rounds} {rounds === 1 ? 'round' : 'rounds'}{marketScan ? ' · market scan' : ''}</div>
              {files.length > 0 && <div><span className="text-muted">Files: </span>{files.length} to read</div>}
              <div><span className="text-muted">Report written by: </span>{health?.devMode ? `${health.crowdModel} (cheaper dev mode)` : health?.analystModel}</div>
              <div><span className="text-muted">Estimated cost: </span><b>${est.toFixed(2)}</b><span className="text-muted"> · stops at ${health?.runBudgetUsd ?? 2}</span></div>
            </div>
            {crowdSize > 300 && <div className="text-xs text-neu">That's a large crowd. A run of 100–300 people is usually enough to check the result first.</div>}
            <div className="flex gap-2 justify-end pt-1">
              <button className="btn btn-ghost" onClick={() => setConfirming(false)}>Cancel</button>
              <button className="btn" autoFocus onClick={() => { setConfirming(false); go() }}>Start run</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Section({ n, title, hint, children }: { n: number; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="card p-5 space-y-4">
      <div className="flex items-start gap-3">
        <span className="w-7 h-7 shrink-0 rounded-full bg-accent/15 text-accent grid place-items-center text-sm font-bold">{n}</span>
        <div>
          <h2 className="font-semibold">{title}</h2>
          {hint && <p className="text-xs text-muted mt-0.5">{hint}</p>}
        </div>
      </div>
      {children}
    </section>
  )
}

function Field({ label, note, wide, children }: { label: string; note?: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <div className={wide ? 'sm:col-span-2' : ''}>
      <div className="text-xs text-muted mb-1">{label}{note && <span className="opacity-70"> · {note}</span>}</div>
      {children}
    </div>
  )
}
