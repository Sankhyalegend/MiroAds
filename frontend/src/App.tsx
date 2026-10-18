import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Users, History as HistoryIcon } from 'lucide-react'
import Upload from './pages/Upload'
import Run from './pages/Run'
import Scorecard from './pages/Scorecard'
import History from './pages/History'
import { useStore } from './store'

function Header() {
  const loc = useLocation()
  const { engine, health, checkBackend } = useStore()
  useEffect(() => { checkBackend() }, [checkBackend])
  const step = loc.pathname === '/' ? 1 : loc.pathname.startsWith('/run') ? 2 : loc.pathname.startsWith('/scorecard') ? 3 : 0
  return (
    <header className="h-14 border-b border-line flex items-center px-4 gap-4 bg-panel/60 backdrop-blur sticky top-0 z-20">
      <Link to="/" className="flex items-center gap-2 font-bold tracking-tight">
        <span className="w-7 h-7 rounded-lg bg-accent text-bg grid place-items-center"><Users size={16} /></span>
        Crowd Validator
      </Link>
      <nav className="ml-6 flex items-center gap-2 text-xs text-muted">
        {['Upload', 'Run', 'Scorecard'].map((s, i) => (
          <span key={s} className={`px-2 py-1 rounded-md ${step === i + 1 ? 'bg-panel-2 text-text' : ''}`}>{i + 1}. {s}</span>
        ))}
        <Link to="/history" className={`px-2 py-1 rounded-md flex items-center gap-1 ${step === 0 ? 'bg-panel-2 text-text' : ''}`}><HistoryIcon size={12} /> History</Link>
      </nav>
      <div className="ml-auto text-xs text-muted flex items-center gap-2">
        {engine === 'live' ? (
          health ? <span className="chip" style={{ borderColor: '#3ddc97', color: '#3ddc97' }}>live · {health.provider === 'fake' ? 'fake provider' : health.crowdModel}{health.devMode && health.provider !== 'fake' ? ' · dev' : ''}</span>
            : <span className="chip" style={{ borderColor: '#ff6b6b', color: '#ff6b6b' }}>backend offline</span>
        ) : <span className="chip">mock engine</span>}
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Header />
      <Routes>
        <Route path="/" element={<Upload />} />
        <Route path="/run" element={<Run />} />
        <Route path="/run/:id" element={<Run />} />
        <Route path="/scorecard" element={<Scorecard />} />
        <Route path="/scorecard/:id" element={<Scorecard />} />
        <Route path="/history" element={<History />} />
      </Routes>
    </BrowserRouter>
  )
}
