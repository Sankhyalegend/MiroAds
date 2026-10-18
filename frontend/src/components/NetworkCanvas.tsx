import { useEffect, useRef, useState } from 'react'
import { Application, Container, Graphics, Sprite, Texture, Text } from 'pixi.js'
import { forceSimulation, forceX, forceY, forceCollide, forceManyBody } from 'd3-force'
import type { Persona, SimEvent } from '../types'
import { GROUP_COLORS, PROFESSION_GROUPS, hexToCss } from '../mock/personas'
import { bus } from '../mock/bus'
import { live } from '../store'

export type EdgeMode = 'all' | 'recent' | 'off'

interface Node { id: number; x: number; y: number; sprite: Sprite; color: number; targetColor: number; pulse: number; flash: number; r: number; degree: number }
/** A connection between two agents. Starts "live" (bright, animated particle), then settles into the persistent web. */
interface Edge {
  from: number; to: number; born: number; color: number; width: number
  kind: 'reply' | 'repost' | 'mind'
  /** Curve bend sign so parallel edges don't overlap. */
  bend: number
}
interface Ripple { from: number; to: number; born: number }

const IDLE = 0x33405c
const LIVE_MS = 1600       // bright, animated phase
const SETTLE_MS = 45000    // fade from "recent" brightness to resting brightness
const MAX_EDGES = 6000
const MAX_RIPPLES = 400

function scoreColor(s: number): number {
  const t = Math.max(0, Math.min(1, s / 10))
  const lerp = (a: number, b: number, k: number) => Math.round(a + (b - a) * k)
  const c1 = [0xff, 0x6b, 0x6b], c2 = [0xf5, 0xc2, 0x42], c3 = [0x3d, 0xdc, 0x97]
  const [a, b, k] = t < 0.5 ? [c1, c2, t * 2] : [c2, c3, (t - 0.5) * 2]
  return (lerp(a[0], b[0], k) << 16) | (lerp(a[1], b[1], k) << 8) | lerp(a[2], b[2], k)
}
function mixColor(a: number, b: number, k: number) {
  const r = ((a >> 16) & 255) + (((b >> 16) & 255) - ((a >> 16) & 255)) * k
  const g = ((a >> 8) & 255) + (((b >> 8) & 255) - ((a >> 8) & 255)) * k
  const bl = (a & 255) + ((b & 255) - (a & 255)) * k
  return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(bl)
}
/** Point on a quadratic curve from a to b bent sideways by `bend`. */
function curvePoint(ax: number, ay: number, bx: number, by: number, bend: number, t: number) {
  const mx = (ax + bx) / 2, my = (ay + by) / 2
  const dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy) || 1
  const cx = mx - (dy / L) * L * 0.18 * bend, cy = my + (dx / L) * L * 0.18 * bend
  const u = 1 - t
  return [u * u * ax + 2 * u * t * cx + t * t * bx, u * u * ay + 2 * u * t * cy + t * t * by, cx, cy] as const
}

export default function NetworkCanvas({ personas, colorMode, edgeMode, onStats }: {
  personas: Persona[]
  colorMode: 'sentiment' | 'profession'
  edgeMode: EdgeMode
  onStats?: (s: { edges: number; crossCluster: number }) => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ p: Persona; x: number; y: number; score: number; degree: number } | null>(null)
  const colorModeRef = useRef(colorMode); colorModeRef.current = colorMode
  const edgeModeRef = useRef(edgeMode); edgeModeRef.current = edgeMode
  const onStatsRef = useRef(onStats); onStatsRef.current = onStats

  useEffect(() => {
    const host = hostRef.current
    if (!host || personas.length === 0) return
    let destroyed = false
    const app = new Application()
    const nodes: Node[] = []
    const edges: Edge[] = []
    const ripples: Ripple[] = []
    let crossCluster = 0
    let unsub = () => {}

    ;(async () => {
      await app.init({ background: 0x0b0f17, resizeTo: host, antialias: true, resolution: Math.min(2, window.devicePixelRatio || 1), autoDensity: true })
      if (destroyed) { app.destroy(true); return }
      host.appendChild(app.canvas)

      const world = new Container()
      app.stage.addChild(world)
      const webLayer = new Graphics()      // persistent conversation web
      const rippleLayer = new Graphics()   // "reading" ripples
      const liveLayer = new Graphics()     // bright live edges + particles
      const nodeLayer = new Container()
      const labelLayer = new Container()
      world.addChild(webLayer, rippleLayer, liveLayer, nodeLayer, labelLayer)

      const g = new Graphics().circle(0, 0, 8).fill(0xffffff)
      const tex: Texture = app.renderer.generateTexture(g)

      // Cluster centres on a ring. Lines crossing the empty middle read as "different groups talking".
      const W = host.clientWidth, H = host.clientHeight
      const R = Math.min(W, H) * 0.37
      const centers = new Map<string, { x: number; y: number }>()
      PROFESSION_GROUPS.forEach((grp, i) => {
        const a = (i / PROFESSION_GROUPS.length) * Math.PI * 2 - Math.PI / 2
        centers.set(grp, { x: W / 2 + Math.cos(a) * R, y: H / 2 + Math.sin(a) * R })
      })

      const base = personas.length > 2000 ? 2.1 : personas.length > 800 ? 3 : 4.2
      type SimNode = { id: number; x: number; y: number; cx: number; cy: number; r: number }
      const simNodes: SimNode[] = personas.map(p => {
        const c = centers.get(p.professionGroup)!
        return { id: p.id, x: c.x + (Math.random() - 0.5) * 60, y: c.y + (Math.random() - 0.5) * 60, cx: c.x, cy: c.y, r: base * (0.75 + p.influence * 1.1) }
      })
      const sim = forceSimulation(simNodes)
        .force('x', forceX<SimNode>(d => d.cx).strength(0.12))
        .force('y', forceY<SimNode>(d => d.cy).strength(0.12))
        .force('charge', forceManyBody().strength(-2))
        .force('collide', forceCollide<SimNode>(d => d.r + 1.3))
        .stop()
      for (let i = 0; i < 170; i++) sim.tick()

      simNodes.forEach((n, i) => {
        const sp = new Sprite(tex)
        sp.anchor.set(0.5)
        sp.width = n.r * 2; sp.height = n.r * 2
        sp.position.set(n.x, n.y)
        sp.tint = IDLE; sp.alpha = 0.92
        nodeLayer.addChild(sp)
        nodes.push({ id: personas[i].id, x: n.x, y: n.y, sprite: sp, color: IDLE, targetColor: IDLE, pulse: 0, flash: 0, r: n.r, degree: 0 })
      })

      PROFESSION_GROUPS.forEach(grp => {
        const c = centers.get(grp)!
        const dx = c.x - W / 2, dy = c.y - H / 2, L = Math.hypot(dx, dy) || 1
        const t = new Text({ text: grp, style: { fill: 0x8b96ad, fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' } })
        t.anchor.set(0.5); t.position.set(c.x + (dx / L) * (R * 0.45), c.y + (dy / L) * (R * 0.45)); t.alpha = 0.85
        labelLayer.addChild(t)
      })

      // Pan & zoom
      let dragging = false, lx = 0, ly = 0
      app.canvas.addEventListener('pointerdown', e => { dragging = true; lx = e.clientX; ly = e.clientY })
      window.addEventListener('pointerup', () => { dragging = false })
      app.canvas.addEventListener('pointermove', e => {
        if (dragging) { world.x += e.clientX - lx; world.y += e.clientY - ly; lx = e.clientX; ly = e.clientY; return }
        const rect = app.canvas.getBoundingClientRect()
        const px = (e.clientX - rect.left - world.x) / world.scale.x
        const py = (e.clientY - rect.top - world.y) / world.scale.y
        let best: Node | null = null, bd = 10 / world.scale.x
        for (const n of nodes) { const d = Math.hypot(n.x - px, n.y - py); if (d < bd) { bd = d; best = n } }
        if (best) { const n = best; setHover({ p: personas[n.id], x: e.clientX - rect.left, y: e.clientY - rect.top, score: live.scores[n.id], degree: n.degree }) }
        else setHover(null)
      })
      app.canvas.addEventListener('pointerleave', () => setHover(null))
      app.canvas.addEventListener('wheel', e => {
        e.preventDefault()
        const rect = app.canvas.getBoundingClientRect()
        const mx = e.clientX - rect.left, my = e.clientY - rect.top
        const k = e.deltaY < 0 ? 1.1 : 1 / 1.1
        const ns = Math.max(0.4, Math.min(5, world.scale.x * k))
        world.x = mx - (mx - world.x) * (ns / world.scale.x)
        world.y = my - (my - world.y) * (ns / world.scale.y)
        world.scale.set(ns)
      }, { passive: false })

      const byId = (id: number) => nodes[id]
      const addEdge = (from: number, to: number, color: number, width: number, kind: Edge['kind']) => {
        if (from === to) return
        edges.push({ from, to, born: performance.now(), color, width, kind, bend: (from + to) % 2 === 0 ? 1 : -1 })
        byId(from).degree++; byId(to).degree++
        if (personas[from].professionGroup !== personas[to].professionGroup) crossCluster++
        if (edges.length > MAX_EDGES) edges.splice(0, edges.length - MAX_EDGES)
      }

      unsub = bus.subscribe((e: SimEvent) => {
        switch (e.kind) {
          case 'impression': { const n = byId(e.agentId); n.targetColor = scoreColor(e.score); n.pulse = Math.max(n.pulse, 0.6); break }
          case 'post': { byId(e.agentId).pulse = 1.4; break }
          case 'reply': {
            byId(e.agentId).pulse = 1
            // colour by stance of the replier: green agrees-ish / red disagrees-ish with the crowd
            addEdge(e.agentId, e.toAgentId, scoreColor(e.score), 1.4, 'reply')
            break
          }
          case 'repost': { byId(e.agentId).pulse = 0.8; addEdge(e.fromAgentId, e.agentId, 0x7c9cff, 1.1, 'repost'); break }
          case 'mind_change': { const n = byId(e.agentId); n.flash = 1; n.targetColor = scoreColor(e.to); addEdge(e.causedBy, e.agentId, 0xffffff, 1.2, 'mind'); break }
          case 'exposure': {
            ripples.push({ from: e.fromAgentId, to: e.agentId, born: performance.now() })
            if (ripples.length > MAX_RIPPLES) ripples.splice(0, ripples.length - MAX_RIPPLES)
            break
          }
        }
      })

      let statTick = 0
      app.ticker.add((tk) => {
        const dt = tk.deltaMS / 1000
        const now = performance.now()
        const mode = colorModeRef.current
        const emode = edgeModeRef.current

        for (const n of nodes) {
          const p = personas[n.id]
          const want = mode === 'profession' ? (live.scores[n.id] < 0 ? IDLE : GROUP_COLORS[p.professionGroup]) : n.targetColor
          if (n.color !== want) { n.color = mixColor(n.color, want, Math.min(1, dt * 6)); if (Math.abs(n.color - want) < 0x010101) n.color = want }
          let c = n.color
          if (n.flash > 0) { c = mixColor(c, 0xffffff, n.flash); n.flash = Math.max(0, n.flash - dt * 2.5) }
          n.sprite.tint = c
          const s = n.r * 2 * (1 + n.pulse * 1.3)
          n.sprite.width = s; n.sprite.height = s
          if (n.pulse > 0) n.pulse = Math.max(0, n.pulse - dt * 2.2)
        }

        // Persistent web: every past interaction stays as a curve. Brightness decays from "recent" to "resting".
        webLayer.clear()
        if (emode !== 'off') {
          for (const ed of edges) {
            const age = now - ed.born
            if (age < LIVE_MS) continue
            if (emode === 'recent' && age > SETTLE_MS) continue
            const k = Math.min(1, (age - LIVE_MS) / SETTLE_MS)
            const alpha = (0.55 - 0.4 * k) * (ed.kind === 'repost' ? 0.8 : 1)
            const a = byId(ed.from), b = byId(ed.to)
            const [, , cx, cy] = curvePoint(a.x, a.y, b.x, b.y, ed.bend, 0.5)
            webLayer.moveTo(a.x, a.y).quadraticCurveTo(cx, cy, b.x, b.y)
              .stroke({ width: ed.kind === 'mind' ? 1.1 : 0.8, color: ed.color, alpha })
          }
        }

        // Reading ripples: thin dashes that travel from poster to reader and vanish.
        rippleLayer.clear()
        for (let i = ripples.length - 1; i >= 0; i--) {
          const rp = ripples[i]
          const age = (now - rp.born) / 900
          if (age >= 1) { ripples.splice(i, 1); continue }
          const a = byId(rp.from), b = byId(rp.to)
          const t0 = Math.max(0, age * 1.4 - 0.4), t1 = Math.min(1, age * 1.4)
          const [x0, y0] = curvePoint(a.x, a.y, b.x, b.y, 0.3, t0)
          const [x1, y1, cx, cy] = curvePoint(a.x, a.y, b.x, b.y, 0.3, t1)
          void cx; void cy
          rippleLayer.moveTo(x0, y0).lineTo(x1, y1).stroke({ width: 0.7, color: 0x9fb4ff, alpha: 0.35 * (1 - age) })
        }

        // Live edges: bright curve drawing itself from sender to receiver, with a particle at the head.
        liveLayer.clear()
        for (const ed of edges) {
          const age = now - ed.born
          if (age >= LIVE_MS) continue
          const prog = Math.min(1, age / (LIVE_MS * 0.55))
          const fade = age > LIVE_MS * 0.55 ? 1 - (age - LIVE_MS * 0.55) / (LIVE_MS * 0.45) : 1
          const a = byId(ed.from), b = byId(ed.to)
          const steps = 14
          liveLayer.moveTo(a.x, a.y)
          for (let s = 1; s <= steps; s++) {
            const [x, y] = curvePoint(a.x, a.y, b.x, b.y, ed.bend, (s / steps) * prog)
            liveLayer.lineTo(x, y)
          }
          liveLayer.stroke({ width: ed.width + 0.6, color: ed.color, alpha: 0.95 * fade })
          const [hx, hy] = curvePoint(a.x, a.y, b.x, b.y, ed.bend, prog)
          liveLayer.circle(hx, hy, 2.4 + ed.width).fill({ color: ed.color, alpha: fade })
          if (prog >= 1) liveLayer.circle(b.x, b.y, b.r + 3 + (1 - fade) * 6).stroke({ width: 1, color: ed.color, alpha: 0.6 * fade })
        }

        if (++statTick % 20 === 0) onStatsRef.current?.({ edges: edges.length, crossCluster })
      })
    })()

    return () => {
      destroyed = true
      unsub()
      try { app.destroy(true, { children: true }) } catch { /* not yet initialised */ }
      if (host.firstChild) host.innerHTML = ''
    }
  }, [personas])

  return (
    <div ref={hostRef} className="relative w-full h-full overflow-hidden rounded-xl" style={{ touchAction: 'none' }}>
      {hover && (
        <div className="absolute z-10 pointer-events-none card p-3 text-xs max-w-[260px] fade-in"
          style={{ left: Math.min(hover.x + 14, (hostRef.current?.clientWidth ?? 800) - 270), top: hover.y + 14 }}>
          <div className="font-semibold text-sm">{hover.p.name}</div>
          <div className="text-muted">{hover.p.profession} · {hover.p.ageBand} · {hover.p.region}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            <span className="chip" style={{ borderColor: hexToCss(GROUP_COLORS[hover.p.professionGroup]) }}>{hover.p.professionGroup}</span>
            <span className="chip">{hover.p.ideology}</span>
            <span className="chip">{hover.p.economic}</span>
            <span className="chip">{hover.p.tech}</span>
            <span className="chip">{hover.p.income} income</span>
            <span className="chip">{hover.p.role}</span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-muted">Influence {(hover.p.influence * 100).toFixed(0)} · {hover.degree} connections</span>
            <span className="font-semibold" style={{ color: hover.score < 0 ? '#8b96ad' : hexToCss(scoreColor(hover.score)) }}>
              {hover.score < 0 ? 'not yet reacted' : `score ${hover.score.toFixed(1)}`}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
