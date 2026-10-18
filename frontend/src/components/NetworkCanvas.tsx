import { useEffect, useRef, useState } from 'react'
import { Application, Container, Graphics, Sprite, Texture } from 'pixi.js'
import { forceSimulation, forceX, forceY, forceCollide, forceManyBody } from 'd3-force'
import type { Persona, SimEvent } from '../types'
import { GROUP_COLORS, PROFESSION_GROUPS, hexToCss } from '../mock/personas'
import { bus } from '../mock/bus'
import { live } from '../store'

interface Node { id: number; x: number; y: number; sprite: Sprite; ring?: Graphics; color: number; pulse: number; flash: number; targetColor: number }
interface Edge { from: number; to: number; born: number; ttl: number; color: number; width: number; kind: 'reply' | 'repost' | 'influence' }

const IDLE = 0x33405c
function scoreColor(s: number): number {
  // red (0) → amber (5) → green (10)
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

export default function NetworkCanvas({ personas, colorMode }: { personas: Persona[]; colorMode: 'sentiment' | 'profession' }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ p: Persona; x: number; y: number; score: number } | null>(null)
  const colorModeRef = useRef(colorMode)
  colorModeRef.current = colorMode

  useEffect(() => {
    const host = hostRef.current
    if (!host || personas.length === 0) return
    let destroyed = false
    const app = new Application()
    const nodes: Node[] = []
    const edges: Edge[] = []
    const influence: Edge[] = []
    let unsub = () => {}

    ;(async () => {
      await app.init({ background: 0x0b0f17, resizeTo: host, antialias: true, resolution: Math.min(2, window.devicePixelRatio || 1), autoDensity: true })
      if (destroyed) { app.destroy(true); return }
      host.appendChild(app.canvas)

      const world = new Container()
      app.stage.addChild(world)
      const edgeLayer = new Graphics()
      const influenceLayer = new Graphics()
      const nodeLayer = new Container()
      const fxLayer = new Graphics()
      world.addChild(influenceLayer, edgeLayer, nodeLayer, fxLayer)

      // Shared circle texture, tinted per node.
      const g = new Graphics().circle(0, 0, 8).fill(0xffffff)
      const tex: Texture = app.renderer.generateTexture(g)

      // Cluster centers by profession group on a ring.
      const W = host.clientWidth, H = host.clientHeight
      const R = Math.min(W, H) * 0.36
      const centers = new Map<string, { x: number; y: number }>()
      PROFESSION_GROUPS.forEach((grp, i) => {
        const a = (i / PROFESSION_GROUPS.length) * Math.PI * 2 - Math.PI / 2
        centers.set(grp, { x: W / 2 + Math.cos(a) * R, y: H / 2 + Math.sin(a) * R })
      })

      const radius = personas.length > 2000 ? 2.2 : personas.length > 800 ? 3.2 : 4.5
      type SimNode = { id: number; x: number; y: number; cx: number; cy: number }
      const simNodes: SimNode[] = personas.map(p => {
        const c = centers.get(p.professionGroup)!
        return { id: p.id, x: c.x + (Math.random() - 0.5) * 60, y: c.y + (Math.random() - 0.5) * 60, cx: c.x, cy: c.y }
      })
      const sim = forceSimulation(simNodes)
        .force('x', forceX<SimNode>(d => d.cx).strength(0.12))
        .force('y', forceY<SimNode>(d => d.cy).strength(0.12))
        .force('charge', forceManyBody().strength(-2))
        .force('collide', forceCollide(radius + 1.2))
        .stop()
      for (let i = 0; i < 160; i++) sim.tick()

      simNodes.forEach((n, i) => {
        const sp = new Sprite(tex)
        sp.anchor.set(0.5)
        sp.width = radius * 2; sp.height = radius * 2
        sp.position.set(n.x, n.y)
        sp.tint = IDLE
        sp.alpha = 0.9
        nodeLayer.addChild(sp)
        nodes.push({ id: personas[i].id, x: n.x, y: n.y, sprite: sp, color: IDLE, targetColor: IDLE, pulse: 0, flash: 0 })
      })

      // Cluster labels
      const labelLayer = new Container()
      world.addChild(labelLayer)
      const { Text } = await import('pixi.js')
      PROFESSION_GROUPS.forEach(grp => {
        const c = centers.get(grp)!
        const t = new Text({ text: grp, style: { fill: 0x8b96ad, fontSize: 11, fontFamily: 'Inter, system-ui, sans-serif' } })
        t.anchor.set(0.5); t.position.set(c.x, c.y - R * 0.42 - 6); t.alpha = 0.8
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
        if (best) {
          const n = best
          setHover({ p: personas[n.id], x: e.clientX - rect.left, y: e.clientY - rect.top, score: live.scores[n.id] })
        } else setHover(null)
      })
      app.canvas.addEventListener('pointerleave', () => setHover(null))
      app.canvas.addEventListener('wheel', e => {
        e.preventDefault()
        const rect = app.canvas.getBoundingClientRect()
        const mx = e.clientX - rect.left, my = e.clientY - rect.top
        const k = e.deltaY < 0 ? 1.1 : 1 / 1.1
        const ns = Math.max(0.4, Math.min(4, world.scale.x * k))
        world.x = mx - (mx - world.x) * (ns / world.scale.x)
        world.y = my - (my - world.y) * (ns / world.scale.y)
        world.scale.set(ns)
      }, { passive: false })

      const byId = (id: number) => nodes[id]
      unsub = bus.subscribe((e: SimEvent) => {
        switch (e.kind) {
          case 'impression': { const n = byId(e.agentId); n.targetColor = scoreColor(e.score); n.pulse = Math.max(n.pulse, 0.6); break }
          case 'post': { const n = byId(e.agentId); n.pulse = 1.4; break }
          case 'reply': {
            const n = byId(e.agentId); n.pulse = 1
            const col = scoreColor(e.score)
            edges.push({ from: e.agentId, to: e.toAgentId, born: performance.now(), ttl: 1800, color: col, width: 1.6, kind: 'reply' })
            if (influence.length < 2500) influence.push({ from: e.agentId, to: e.toAgentId, born: 0, ttl: 0, color: col, width: 0.5, kind: 'influence' })
            break
          }
          case 'repost': {
            const n = byId(e.agentId); n.pulse = 0.8
            edges.push({ from: e.fromAgentId, to: e.agentId, born: performance.now(), ttl: 1500, color: 0x7c9cff, width: 1.1, kind: 'repost' })
            break
          }
          case 'mind_change': {
            const n = byId(e.agentId); n.flash = 1; n.targetColor = scoreColor(e.to)
            edges.push({ from: e.causedBy, to: e.agentId, born: performance.now(), ttl: 1200, color: 0xffffff, width: 0.9, kind: 'repost' })
            break
          }
        }
      })

      app.ticker.add((tk) => {
        const dt = tk.deltaMS / 1000
        const now = performance.now()
        const mode = colorModeRef.current
        // nodes
        for (const n of nodes) {
          const p = personas[n.id]
          const want = mode === 'profession' ? (live.scores[n.id] < 0 ? IDLE : GROUP_COLORS[p.professionGroup]) : n.targetColor
          if (n.color !== want) { n.color = mixColor(n.color, want, Math.min(1, dt * 6)); if (Math.abs(n.color - want) < 0x010101) n.color = want }
          let c = n.color
          if (n.flash > 0) { c = mixColor(c, 0xffffff, n.flash); n.flash = Math.max(0, n.flash - dt * 2.5) }
          n.sprite.tint = c
          const s = radius * 2 * (1 + n.pulse * 1.3)
          n.sprite.width = s; n.sprite.height = s
          if (n.pulse > 0) n.pulse = Math.max(0, n.pulse - dt * 2.2)
        }
        // influence graph (faint, persistent)
        influenceLayer.clear()
        for (const ed of influence) {
          const a = byId(ed.from), b = byId(ed.to)
          influenceLayer.moveTo(a.x, a.y).lineTo(b.x, b.y)
        }
        influenceLayer.stroke({ width: 0.5, color: 0x7c9cff, alpha: 0.07 })
        // active arrows
        edgeLayer.clear()
        fxLayer.clear()
        for (let i = edges.length - 1; i >= 0; i--) {
          const ed = edges[i]
          const age = (now - ed.born) / ed.ttl
          if (age >= 1) { edges.splice(i, 1); continue }
          const a = byId(ed.from), b = byId(ed.to)
          const alpha = (1 - age) * 0.9
          const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy) || 1
          const ux = dx / L, uy = dy / L
          // travelling head along the edge for the first 40% of life, then fade.
          const prog = Math.min(1, age / 0.4)
          const hx = a.x + dx * prog, hy = a.y + dy * prog
          edgeLayer.moveTo(a.x, a.y).lineTo(hx, hy).stroke({ width: ed.width, color: ed.color, alpha })
          const ah = 5 + ed.width * 2
          fxLayer.poly([hx, hy, hx - ux * ah - uy * ah * 0.5, hy - uy * ah + ux * ah * 0.5, hx - ux * ah + uy * ah * 0.5, hy - uy * ah - ux * ah * 0.5]).fill({ color: ed.color, alpha })
        }
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
            <span className="text-muted">Influence {(hover.p.influence * 100).toFixed(0)}</span>
            <span className="font-semibold" style={{ color: hover.score < 0 ? '#8b96ad' : hexToCss(scoreColor(hover.score)) }}>
              {hover.score < 0 ? 'not yet reacted' : `score ${hover.score.toFixed(1)}`}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
