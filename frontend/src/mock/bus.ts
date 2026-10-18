import type { SimEvent } from '../types'

// Tiny event bus. The store subscribes for counters and the feed; the canvas
// subscribes for visuals. Keeps high-frequency events out of React state.
type Handler = (e: SimEvent) => void
const handlers = new Set<Handler>()

export const bus = {
  subscribe(fn: Handler) { handlers.add(fn); return () => { handlers.delete(fn) } },
  emit(e: SimEvent) { handlers.forEach(h => h(e)) },
}
