import { useEffect, useState } from 'react'
import { getPlaybook } from '../api'
import type { Playbook } from '../types'

export function PlaybookDrawer({ onClose }: { onClose: () => void }) {
  const [playbook, setPlaybook] = useState<Playbook | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getPlaybook()
      .then((next) => {
        if (!cancelled) setPlaybook(next)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load the playbook.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="drawer-back" onClick={onClose} role="presentation">
      <aside
        className="drawer stack"
        role="dialog"
        aria-label="NDA playbook"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="row-between">
          <p className="eyebrow">Policy is data</p>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>
        <h2 className="serif" style={{ margin: 0 }}>
          {playbook?.name ?? 'Playbook'}
        </h2>
        <p className="muted">
          These ten positions are the company&apos;s rules. The screen does not edit them. The
          model is not allowed to grade them.
        </p>
        {error && <p className="error">{error}</p>}
        {playbook?.positions.map((position) => (
          <article key={position.id} className="position">
            <div className="row-between">
              <strong>{position.title}</strong>
              <span className="mono faint">{position.critical ? 'critical' : 'standard'}</span>
            </div>
            <p className="muted" style={{ marginBottom: 0 }}>
              {position.requirement}
            </p>
            <p className="faint mono">If absent: {position.if_absent}</p>
          </article>
        ))}
      </aside>
    </div>
  )
}
