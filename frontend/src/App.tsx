import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Users } from 'lucide-react'
import Upload from './pages/Upload'
import Run from './pages/Run'
import Scorecard from './pages/Scorecard'

function Header() {
  const loc = useLocation()
  const step = loc.pathname === '/' ? 1 : loc.pathname === '/run' ? 2 : 3
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
      </nav>
      <div className="ml-auto text-xs text-muted">mock engine · frontend preview</div>
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
        <Route path="/scorecard" element={<Scorecard />} />
      </Routes>
    </BrowserRouter>
  )
}
