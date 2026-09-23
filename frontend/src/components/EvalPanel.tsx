import { useEffect, useState } from 'react'
import { getEvals, runEval } from '../api'
import type { EvalBundle, ReviewMode } from '../types'
import { RouteChip } from './RouteChip'

export function EvalPanel() {
  const [bundle, setBundle] = useState<EvalBundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState<ReviewMode | null>(null)

  async function load() {
    setBundle(await getEvals())
  }

  useEffect(() => {
    let cancelled = false
    load().catch((err: unknown) => {
      if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load eval.')
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function run(mode: ReviewMode) {
    setError(null)
    setRunning(mode)
    try {
      await runEval(mode)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Eval failed.')
    } finally {
      setRunning(null)
    }
  }

  const fixture = bundle?.fixture

  return (
    <div className="stack">
      <p className="lede">
        False-green means the system painted a contract green when the labeled route was not
        green. That is the number a general counsel should see. This is a demo set of eight
        contracts, not a CUAD benchmark. Live runs are shown apart from the fixture baseline.
      </p>
      {error && <p className="error">{error}</p>}
      {fixture && (
        <section className="panel">
          <p className="eyebrow">Fixture baseline</p>
          <p className="stat">
            {fixture.false_green}/{fixture.sample_count}
          </p>
          <p className="muted">false-green</p>
          <div className="grid-2">
            <p>
              Route match {fixture.route_correct}/{fixture.sample_count}
            </p>
            <p>
              False accepts {fixture.false_accept}/{fixture.false_accept_base}
            </p>
            <p>Citation failures {fixture.citation_failures}</p>
          </div>
        </section>
      )}
      <div className="nav">
        <button type="button" className="secondary" disabled={running !== null} onClick={() => void run('fixture')}>
          {running === 'fixture' ? 'Running fixture…' : 'Recompute fixture'}
        </button>
        <button type="button" className="primary" disabled={running !== null} onClick={() => void run('live')}>
          {running === 'live' ? 'Calling the local model…' : 'Run live eval'}
        </button>
      </div>
      {bundle?.live && (
        <section className="panel">
          <p className="eyebrow">Last live run</p>
          <p className="stat">
            {bundle.live.false_green}/{bundle.live.sample_count}
          </p>
          <p className="muted">
            false-green · route match {bundle.live.route_correct}/{bundle.live.sample_count} ·
            citation failures {bundle.live.citation_failures}
          </p>
        </section>
      )}
      {fixture && (
        <table className="table">
          <thead>
            <tr>
              <th>Contract</th>
              <th>Gold</th>
              <th>Fixture</th>
              <th>Live</th>
            </tr>
          </thead>
          <tbody>
            {fixture.rows.map((row) => {
              const liveRow = bundle?.live?.rows.find((item) => item.id === row.id)
              return (
                <tr key={row.id}>
                  <td>{row.title}</td>
                  <td>
                    <RouteChip route={row.gold_route} />
                  </td>
                  <td>
                    <RouteChip route={row.predicted_route} />
                  </td>
                  <td>{liveRow ? <RouteChip route={liveRow.predicted_route} /> : <span className="faint">—</span>}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
