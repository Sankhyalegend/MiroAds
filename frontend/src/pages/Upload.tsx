import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Image, Globe, Tag, Lightbulb, Users, Play } from 'lucide-react'
import { useStore } from '../store'
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
    brief: 'A tool where marketers upload a creative or offer and a crowd of 1,000 AI personas with different jobs, incomes and ideologies react, argue, and produce a scorecard: objections, missing KPIs, and better variants. $49 per run or $299/month. Target: growth teams at 20-200 person startups.',
  },
}

export default function Upload() {
  const nav = useNavigate()
  const { setStimulus, crowdSize, setCrowdSize, rounds, setRounds, start } = useStore()
  const [type, setType] = useState<StimulusType>('creative')
  const [title, setTitle] = useState(SAMPLE.creative.title)
  const [brief, setBrief] = useState(SAMPLE.creative.brief)
  const [url, setUrl] = useState('')
  const [imageUrl, setImageUrl] = useState<string | undefined>()
  const [offer, setOffer] = useState({ product: 'Nightshift smart desk lamp', price: '$149', discount: '$30 off first 500 units', urgency: 'Ends 7 November', terms: '2-year warranty, no subscription' })
  const [audience, setAudience] = useState('Remote software developers 25-40, students, productivity enthusiasts; plus a general-public control sample')

  const pickType = (t: StimulusType) => { setType(t); setTitle(SAMPLE[t].title); setBrief(SAMPLE[t].brief) }

  const onFile = (f: File | undefined) => {
    if (!f) return
    const r = new FileReader()
    r.onload = () => setImageUrl(String(r.result))
    r.readAsDataURL(f)
    if (!title) setTitle(f.name)
  }

  const go = () => {
    const s: Stimulus = {
      type, title: title || 'Untitled', targetAudience: audience,
      brief: type === 'offer'
        ? `${offer.product}. Price ${offer.price}. ${offer.discount}. ${offer.urgency}. Terms: ${offer.terms}. ${brief}`
        : type === 'website' ? `Website ${url}. ${brief}` : brief,
      imageUrl, url: url || undefined, offer: type === 'offer' ? offer : undefined,
    }
    setStimulus(s)
    start()
    nav('/run')
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">What should the crowd judge?</h1>
        <p className="text-muted mt-1">Upload a stimulus. A crowd of simulated people with different jobs, incomes, ideologies and personalities will react, argue, and score it.</p>
      </div>

      <div className="grid md:grid-cols-[1fr_320px] gap-5">
        <div className="card p-5 space-y-5">
          <div className="flex flex-wrap gap-2">
            {TYPES.map(t => (
              <button key={t.id} className="tab flex items-center gap-2" data-active={type === t.id} onClick={() => pickType(t.id)} title={t.hint}>
                {t.icon}{t.label}
              </button>
            ))}
          </div>

          <div>
            <label className="text-xs text-muted">Title</label>
            <input className="input mt-1" value={title} onChange={e => setTitle(e.target.value)} />
          </div>

          {type === 'creative' && (
            <div>
              <label className="text-xs text-muted">Image (optional in the mock; the real engine runs it through a vision model)</label>
              <div className="mt-1 flex gap-3 items-start">
                <label className="btn btn-ghost cursor-pointer">
                  <Image size={16} /> Choose image
                  <input type="file" accept="image/*" className="hidden" onChange={e => onFile(e.target.files?.[0])} />
                </label>
                {imageUrl && <img src={imageUrl} alt="" className="h-24 rounded-lg border border-line object-cover" />}
              </div>
            </div>
          )}

          {type === 'website' && (
            <div>
              <label className="text-xs text-muted">URL</label>
              <input className="input mt-1" placeholder="https://" value={url} onChange={e => setUrl(e.target.value)} />
            </div>
          )}

          {type === 'offer' && (
            <div className="grid grid-cols-2 gap-3">
              {(['product', 'price', 'discount', 'urgency', 'terms'] as const).map(k => (
                <div key={k} className={k === 'terms' ? 'col-span-2' : ''}>
                  <label className="text-xs text-muted capitalize">{k}</label>
                  <input className="input mt-1" value={offer[k]} onChange={e => setOffer({ ...offer, [k]: e.target.value })} />
                </div>
              ))}
            </div>
          )}

          <div>
            <label className="text-xs text-muted">{type === 'idea' ? 'Describe the idea' : 'Describe what the crowd sees'}</label>
            <textarea className="input mt-1 min-h-[140px]" value={brief} onChange={e => setBrief(e.target.value)} />
          </div>

          <div>
            <label className="text-xs text-muted">Target audience (the crowd is stratified toward this, with a contrarian quota)</label>
            <input className="input mt-1" value={audience} onChange={e => setAudience(e.target.value)} />
          </div>
        </div>

        <div className="space-y-5">
          <div className="card p-5 space-y-4">
            <div className="flex items-center gap-2 font-semibold"><Users size={16} /> Crowd</div>
            <div>
              <div className="flex justify-between text-sm"><span className="text-muted">Size</span><span className="font-semibold">{crowdSize.toLocaleString()} agents</span></div>
              <input type="range" min={100} max={3000} step={100} value={crowdSize} onChange={e => setCrowdSize(Number(e.target.value))} className="w-full mt-2 accent-[#7c9cff]" />
              <div className="text-xs text-muted mt-1">Est. cost on Haiku 5.5: ${(crowdSize * (rounds + 1) * 0.00045).toFixed(2)} crowd + ~$1.70 judge &amp; experts</div>
            </div>
            <div>
              <div className="flex justify-between text-sm"><span className="text-muted">Social rounds</span><span className="font-semibold">{rounds}</span></div>
              <input type="range" min={2} max={10} value={rounds} onChange={e => setRounds(Number(e.target.value))} className="w-full mt-2 accent-[#7c9cff]" />
            </div>
            <div className="text-xs text-muted leading-relaxed">
              10 profession groups · 4 ideologies · 3 spending stances · 5 tech-adoption stages · 5 income bands · 5 decision roles. Heavy-tailed influence so a few voices carry.
            </div>
          </div>

          <button className="btn w-full justify-center text-base py-3" onClick={go}>
            <Play size={18} /> Run the crowd
          </button>
          <div className="text-xs text-muted text-center">Mock engine: opinions are derived from persona attributes. Swap in the LLM backend without changing the UI.</div>
        </div>
      </div>
    </div>
  )
}
