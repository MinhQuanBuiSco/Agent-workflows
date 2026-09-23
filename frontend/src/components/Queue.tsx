import { useEffect, useState } from 'react'
import { DEMO_PDF_URL, getLlm, getMatters, getSamples, openDemo, openSample, uploadContract } from '../api'
import type { LlmStatus, Matter, MatterSummary, ReviewMode, Sample } from '../types'
import { RouteChip } from './RouteChip'

interface QueueProps {
  mode: ReviewMode
  onMode: (mode: ReviewMode) => void
  onOpenExisting: (id: string) => void
  onStartReview: (id: string) => void
}

export function Queue({ mode, onMode, onOpenExisting, onStartReview }: QueueProps) {
  const [samples, setSamples] = useState<Sample[]>([])
  const [matters, setMatters] = useState<MatterSummary[]>([])
  const [llm, setLlm] = useState<LlmStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function reload() {
    const [nextSamples, nextMatters, nextLlm] = await Promise.all([
      getSamples(),
      getMatters(),
      getLlm(),
    ])
    setSamples(nextSamples)
    setMatters(nextMatters)
    setLlm(nextLlm)
  }

  useEffect(() => {
    let cancelled = false
    reload().catch((err: unknown) => {
      if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load the queue.')
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function startSample(sample: Sample) {
    setError(null)
    setBusy(sample.id)
    try {
      const matter = await openSample(sample.id)
      onStartReview(matter.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open that sample.')
    } finally {
      setBusy(null)
    }
  }

  async function startUpload(key: string, create: () => Promise<Matter>) {
    setError(null)
    if (mode !== 'live') {
      setError('Uploaded contracts have no recorded extraction. Switch to live mode first.')
      return
    }
    if (!llm?.reachable) {
      setError('The local model server is not reachable. Start mlx_lm.server on port 8080.')
      return
    }
    setBusy(key)
    try {
      const matter = await create()
      onStartReview(matter.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="stack">
      <p className="lede">
        Incoming NDAs are scored against Acme&apos;s playbook. The model may only quote the
        contract. Python assigns green, yellow, or red. A quote that is not in the document
        cannot clear a position.
      </p>
      <div className="row-between">
        <div className="mode" role="group" aria-label="Review mode">
          <button type="button" aria-pressed={mode === 'fixture'} onClick={() => onMode('fixture')}>
            Fixture
          </button>
          <button
            type="button"
            aria-pressed={mode === 'live'}
            onClick={() => onMode('live')}
            disabled={!llm?.reachable}
            title={llm?.reachable ? 'Call the local model' : 'Model server is offline'}
          >
            Live
          </button>
        </div>
        <span className={llm?.reachable ? 'badge ok' : 'badge down'}>
          {llm?.reachable ? 'Model server on' : 'Model server off'}
        </span>
      </div>
      {mode === 'live' && !llm?.reachable && (
        <p className="error">
          Live mode stays disabled until mlx_lm.server answers on port 8080. Fixture mode still
          replays the recorded extractions.
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <section className="panel stack">
        <div className="row-between">
          <h2 className="serif" style={{ margin: 0, fontSize: '1.7rem' }}>
            Samples
          </h2>
          <div className="nav">
            <button
              type="button"
              className="secondary"
              disabled={busy !== null}
              title="A mutual NDA with a few off-playbook terms. Live mode only."
              onClick={() => void startUpload('demo', openDemo)}
            >
              Use demo PDF
            </button>
            <label className="file secondary">
              Upload PDF or TXT
              <input
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) void startUpload('upload', () => uploadContract(file))
                  event.target.value = ''
                }}
              />
            </label>
          </div>
        </div>
        <p className="faint" style={{ margin: 0 }}>
          No contract at hand? <strong>Use demo PDF</strong> runs a live review of a synthetic
          Bluefin Analytics NDA.{' '}
          <a href={DEMO_PDF_URL} target="_blank" rel="noreferrer" className="link">
            Open the PDF
          </a>
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>Counterparty</th>
              <th>Paper</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {samples.map((sample) => (
              <tr key={sample.id}>
                <td>{sample.counterparty}</td>
                <td>
                  <div>{sample.title}</div>
                  <div className="faint">{sample.summary}</div>
                </td>
                <td>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy === sample.id}
                    onClick={() => void startSample(sample)}
                  >
                    Review
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel stack">
        <h2 className="serif" style={{ margin: 0, fontSize: '1.7rem' }}>
          Matters
        </h2>
        {matters.length === 0 ? (
          <p className="muted">No matters yet. Review a sample to open the desk.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Matter</th>
                <th>Route</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {matters.map((matter) => (
                <tr key={matter.id}>
                  <td>
                    <div>{matter.counterparty || matter.title}</div>
                    <div className="faint mono">{matter.filename}</div>
                  </td>
                  <td>{matter.route ? <RouteChip route={matter.route} /> : <span className="faint">Not reviewed</span>}</td>
                  <td className="mono">{matter.status.replaceAll('_', ' ')}</td>
                  <td>
                    <button type="button" className="secondary" onClick={() => onOpenExisting(matter.id)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
