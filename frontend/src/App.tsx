import { useEffect, useState } from 'react'
import { EvalPanel } from './components/EvalPanel'
import { Queue } from './components/Queue'
import { ReviewDesk } from './components/ReviewDesk'
import { useReview } from './hooks/useReview'
import type { ReviewMode } from './types'

type Screen = { name: 'queue' } | { name: 'review'; id: string } | { name: 'eval' }

// Eval is for whoever maintains the playbook, not for the demo. VITE_SHOW_EVAL=true brings it back.
const SHOW_EVAL = import.meta.env.VITE_SHOW_EVAL === 'true'

export function App() {
  const [screen, setScreen] = useState<Screen>({ name: 'queue' })
  const [mode, setMode] = useState<ReviewMode>(() => {
    try {
      return localStorage.getItem('playbook-mode') === 'live' ? 'live' : 'fixture'
    } catch {
      return 'fixture'
    }
  })
  const [theme, setTheme] = useState<'light' | 'dark'>(
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const review = useReview()

  useEffect(() => {
    try {
      localStorage.setItem('playbook-mode', mode)
    } catch {
      // A blocked storage only means the mode resets on reload.
    }
  }, [mode])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('playbook-theme', theme)
  }, [theme])

  function openReview(id: string) {
    review.reset()
    setScreen({ name: 'review', id })
  }

  return (
    <div className="shell">
      <header className="letterhead">
        <div className="brand">
          <p className="eyebrow">Acme legal ops</p>
          <h1>Playbook review</h1>
        </div>
        <nav className="nav">
          <button
            type="button"
            aria-current={screen.name === 'queue' ? 'page' : undefined}
            onClick={() => setScreen({ name: 'queue' })}
          >
            Queue
          </button>
          {SHOW_EVAL && (
            <button
              type="button"
              aria-current={screen.name === 'eval' ? 'page' : undefined}
              onClick={() => setScreen({ name: 'eval' })}
            >
              Eval
            </button>
          )}
          <button
            type="button"
            onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
          >
            {theme === 'dark' ? 'Paper' : 'Ink'}
          </button>
        </nav>
      </header>
      <main style={{ paddingTop: '1.25rem' }}>
        {screen.name === 'queue' && (
          <Queue
            mode={mode}
            onMode={setMode}
            onOpenExisting={openReview}
            onStartReview={(id) => {
              openReview(id)
              void review.run(id, mode)
            }}
          />
        )}
        {screen.name === 'review' && (
          <ReviewDesk
            matterId={screen.id}
            mode={mode}
            review={review}
            onBack={() => setScreen({ name: 'queue' })}
          />
        )}
        {SHOW_EVAL && screen.name === 'eval' && <EvalPanel />}
      </main>
    </div>
  )
}
