import { useEffect, useState } from 'react'
import { decide, getMatter } from '../api'
import type { ReviewState } from '../hooks/useReview'
import type { Matter, Position, ReviewMode, Verdict } from '../types'
import { AgentTrace } from './AgentTrace'
import { PlaybookDrawer } from './PlaybookDrawer'
import { RouteChip } from './RouteChip'

const ROUTE_HEADLINE: Record<string, string> = {
  green: 'Clear to send standard paper.',
  yellow: 'Counsel should spend about ten minutes here.',
  red: 'Negotiate. Do not approve this as-is.',
  out_of_playbook: 'This is not an NDA. The playbook does not score it.',
}

interface ReviewDeskProps {
  matterId: string
  mode: ReviewMode
  review: ReviewState
  onBack: () => void
}

export function ReviewDesk({ matterId, mode, review, onBack }: ReviewDeskProps) {
  const [matter, setMatter] = useState<Matter | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [playbookOpen, setPlaybookOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  const { attach, matterId: tracedId } = review
  useEffect(() => {
    // Opening a matter from the queue replays its last trace, and follows it if it is running.
    if (tracedId !== matterId) void attach(matterId)
  }, [matterId, tracedId, attach])

  const resultId = review.result?.id
  useEffect(() => {
    // Refetch rather than trust the trace's result: counsel may have changed it since.
    let cancelled = false
    getMatter(matterId)
      .then((next) => {
        if (!cancelled) setMatter(next)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load the matter.')
      })
    return () => {
      cancelled = true
    }
  }, [matterId, resultId])

  useEffect(() => {
    if (!activeId) return
    document.getElementById('active-excerpt')?.scrollIntoView({ block: 'center' })
  }, [activeId, matter?.id])

  const active = matter?.positions.find((position) => position.id === activeId) ?? null
  const canRun = matter !== null && matter.status !== 'approved' && !review.running
  const needsLive = matter !== null && !matter.sample_id && mode !== 'live'

  async function submit(
    action: 'approve' | 'approve_with_exceptions',
  ) {
    if (!matter) return
    setSaving(true)
    setError(null)
    try {
      const next = await decide(matter.id, { action, note })
      setMatter(next)
      setNote('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not record the decision.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="stack">
      <div className="row-between">
        <button type="button" className="ghost" onClick={onBack}>
          Back to queue
        </button>
        <div className="nav">
          <span className="mono faint">
            {review.matterId === matterId && review.started ? review.started.mode : mode} mode
          </span>
          <button type="button" className="secondary" onClick={() => setPlaybookOpen(true)}>
            Playbook
          </button>
          {matter?.route && matter.status !== 'approved' && (
            <button
              type="button"
              className="secondary"
              disabled={!canRun || needsLive}
              title={needsLive ? 'Uploads have no recording. Switch to live mode.' : undefined}
              onClick={() => void review.run(matter.id, mode)}
            >
              Run again
            </button>
          )}
        </div>
      </div>

      {review.matterId === matterId && <AgentTrace key={matterId} trace={review} />}
      {review.error && <p className="error">{review.error}</p>}
      {error && <p className="error">{error}</p>}

      {matter && !matter.route && !review.running && (
        <section className="panel stack">
          <p className="eyebrow">{matter.counterparty || matter.filename}</p>
          <h2 className="serif" style={{ margin: 0 }}>
            Not reviewed yet
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            {needsLive
              ? 'This is an upload, so there is no recorded extraction. Switch to live mode in the queue to review it.'
              : `Run the review in ${mode} mode and watch each step in the trace.`}
          </p>
          <div>
            <button
              type="button"
              className="primary"
              disabled={!canRun || needsLive}
              onClick={() => void review.run(matter.id, mode)}
            >
              Run review
            </button>
          </div>
        </section>
      )}

      {matter?.route && (
        <>
          <section className={`banner ${matter.route}`}>
            <RouteChip route={matter.route} />
            <h2>{ROUTE_HEADLINE[matter.route]}</h2>
            <ul>
              {matter.route_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            {matter.model_route && matter.model_route !== matter.route && (
              <p className="mono">
                Model route stays {matter.model_route}. Eval does not read this override.
              </p>
            )}
          </section>

          <div className="grid-2">
            <article className="panel">
              <p className="eyebrow">{matter.counterparty || matter.filename}</p>
              <h2 className="serif" style={{ marginTop: 0 }}>
                {matter.title}
              </h2>
              <div className="contract">
                <ContractText text={matter.text} excerpt={active?.excerpt ?? null} />
              </div>
            </article>
            <div className="stack">
              {matter.positions.length === 0 && (
                <p className="muted">No NDA positions were scored.</p>
              )}
              {matter.positions.map((position) => (
                <PositionCard
                  key={position.id}
                  matterId={matter.id}
                  position={position}
                  active={position.id === activeId}
                  closed={matter.status === 'approved'}
                  onSelect={() => setActiveId(position.id)}
                  onSaved={setMatter}
                  onError={setError}
                />
              ))}
              <DecisionBar
                matter={matter}
                note={note}
                onNote={setNote}
                saving={saving}
                onApprove={() => void submit('approve')}
                onExceptions={() => void submit('approve_with_exceptions')}
              />
              <AuditList matter={matter} />
            </div>
          </div>
        </>
      )}
      {playbookOpen && <PlaybookDrawer onClose={() => setPlaybookOpen(false)} />}
    </div>
  )
}

function ContractText({ text, excerpt }: { text: string; excerpt: string | null }) {
  if (!excerpt) return <>{text}</>
  const index = text.indexOf(excerpt)
  if (index < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, index)}
      <mark id="active-excerpt">{excerpt}</mark>
      {text.slice(index + excerpt.length)}
    </>
  )
}

function PositionCard({
  matterId,
  position,
  active,
  closed,
  onSelect,
  onSaved,
  onError,
}: {
  matterId: string
  position: Position
  active: boolean
  closed: boolean
  onSelect: () => void
  onSaved: (matter: Matter) => void
  onError: (message: string) => void
}) {
  const [verdict, setVerdict] = useState<Verdict>(position.verdict === 'ungrounded' ? 'reject' : position.verdict)
  const [note, setNote] = useState('')
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setVerdict(position.verdict === 'ungrounded' ? 'reject' : position.verdict)
  }, [position.verdict, position.human_note])

  async function save() {
    setSaving(true)
    try {
      const next = await decide(matterId, {
        action: 'override',
        overrides: [{ position_id: position.id, verdict, note }],
      })
      onSaved(next)
      setNote('')
      setOpen(false)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Override failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <article className={active ? 'position active' : 'position'}>
      <button type="button" className="ghost" onClick={onSelect} style={{ padding: 0 }}>
        <strong>{position.title}</strong>
      </button>
      <div className="row-between">
        <span className={`route ${tone(position.verdict)}`}>{position.verdict}</span>
        <span className="mono faint">{position.critical ? 'critical' : 'standard'}</span>
      </div>
      {position.excerpt ? (
        <p className="quote">{position.excerpt}</p>
      ) : (
        <p className="faint">Not in the contract.</p>
      )}
      <p className="muted" style={{ marginBottom: 0 }}>
        {position.rationale}
      </p>
      {position.overridden && (
        <p className="mono">
          Model said {position.model_verdict}. Note: {position.human_note}
        </p>
      )}
      {position.comment && <div className="comment">{position.comment}</div>}
      {!closed && (
        <div className="stack" style={{ marginTop: '0.6rem' }}>
          <button type="button" className="ghost" onClick={() => setOpen((value) => !value)}>
            {open ? 'Cancel override' : 'Change verdict'}
          </button>
          {open && (
            <>
              <select value={verdict} onChange={(event) => setVerdict(event.target.value as Verdict)}>
                <option value="accept">accept</option>
                <option value="fallback">fallback</option>
                <option value="reject">reject</option>
              </select>
              <textarea
                rows={2}
                value={note}
                placeholder="Why are you changing this?"
                onChange={(event) => setNote(event.target.value)}
              />
              <button type="button" className="secondary" disabled={saving || note.trim().length < 3} onClick={() => void save()}>
                Save override
              </button>
            </>
          )}
        </div>
      )}
    </article>
  )
}

function tone(verdict: Verdict): string {
  if (verdict === 'accept') return 'green'
  if (verdict === 'fallback') return 'yellow'
  if (verdict === 'reject' || verdict === 'ungrounded') return 'red'
  return 'out_of_playbook'
}

function DecisionBar({
  matter,
  note,
  onNote,
  saving,
  onApprove,
  onExceptions,
}: {
  matter: Matter
  note: string
  onNote: (value: string) => void
  saving: boolean
  onApprove: () => void
  onExceptions: () => void
}) {
  if (matter.status === 'approved') {
    return (
      <section className="panel">
        <p className="eyebrow">Closed</p>
        <p style={{ marginBottom: 0 }}>
          {matter.disposition === 'approved'
            ? 'Approved on a green route.'
            : `Approved with exceptions. Route remains ${matter.route}.`}
        </p>
      </section>
    )
  }
  return (
    <section className="panel stack">
      <p className="eyebrow">Counsel</p>
      {matter.route === 'green' ? (
        <button type="button" className="primary" disabled={saving} onClick={onApprove}>
          Approve
        </button>
      ) : (
        <>
          <textarea
            rows={2}
            value={note}
            placeholder="Note for the exception. This does not turn the route green."
            onChange={(event) => onNote(event.target.value)}
          />
          <button
            type="button"
            className="primary"
            disabled={saving || note.trim().length < 3}
            onClick={onExceptions}
          >
            Approve with exceptions
          </button>
        </>
      )}
    </section>
  )
}

function AuditList({ matter }: { matter: Matter }) {
  return (
    <section className="panel">
      <p className="eyebrow">Audit</p>
      <ul className="stack" style={{ paddingLeft: '1rem' }}>
        {matter.audit.map((event) => (
          <li key={event.id}>
            <span className="mono faint">{event.kind}</span> {event.detail}
          </li>
        ))}
      </ul>
    </section>
  )
}
