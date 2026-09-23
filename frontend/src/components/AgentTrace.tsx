import { useEffect, useRef, useState } from 'react'
import { STAGES, type ReviewState, type Stage } from '../hooks/useReview'
import type { Fields, ModelCall, RuleEvent, Verdict } from '../types'
import { RouteChip } from './RouteChip'

const VERDICTS: Verdict[] = ['accept', 'fallback', 'reject', 'ungrounded']

export function AgentTrace({ trace }: { trace: ReviewState }) {
  const now = useNow(trace.running)
  const [openPref, setOpen] = useState<boolean | null>(null)
  const open = openPref ?? (trace.running || !trace.result)
  const replay = trace.started?.mode === 'fixture'
  const elapsed = trace.running && trace.clockStart ? now - trace.clockStart : trace.lastT
  const currentMessage = trace.current ? trace.stages[trace.current].message : null

  if (!trace.started && !trace.running) return null

  return (
    <section className="trace panel" aria-label="Agent trace">
      <div className="row-between">
        <div className="trace-title">
          <p className="eyebrow">Agent trace</p>
          <span className={replay ? 'lane-badge replay' : 'lane-badge model'}>
            {replay ? 'Replay · model not called' : `Live · ${shortModel(trace.started?.model)}`}
          </span>
          <span className="mono faint">{formatMs(elapsed)}</span>
        </div>
        <button type="button" className="ghost" onClick={() => setOpen(!open)}>
          {open ? 'Hide details' : 'Show details'}
        </button>
      </div>

      <Swimlane stages={trace.stages} running={trace.running} clockStart={trace.clockStart} now={now} />

      {currentMessage && (
        <p className="trace-now">
          <span className="pulse" aria-hidden="true" />
          {currentMessage}
        </p>
      )}

      {open && (
        <div className="trace-body">
          <ModelConsole trace={trace} now={now} />
          <Checks trace={trace} />
          <Router trace={trace} />
        </div>
      )}
    </section>
  )
}

function Swimlane({
  stages,
  running,
  clockStart,
  now,
}: {
  stages: Record<string, Stage>
  running: boolean
  clockStart: number | null
  now: number
}) {
  return (
    <div className="swimlane">
      <div className="lane-label model" style={{ gridRow: 1 }}>
        Model
        <small>proposes</small>
      </div>
      <div className="lane-label python" style={{ gridRow: 2 }}>
        Python
        <small>decides</small>
      </div>
      <div className="lane-track model" style={{ gridRow: 1 }} aria-hidden="true" />
      <div className="lane-track python" style={{ gridRow: 2 }} aria-hidden="true" />
      {STAGES.map(({ step, lane, label }, index) => {
        const stage = stages[step]
        const live =
          stage.status === 'running' && running && clockStart !== null && stage.startT !== null
            ? now - clockStart - stage.startT
            : null
        return (
          <div
            key={step}
            className={`node ${lane} ${stage.status}`}
            style={{ gridRow: lane === 'model' ? 1 : 2, gridColumn: index + 2 }}
            title={stage.message || undefined}
          >
            <span className="node-icon" aria-hidden="true">
              {ICON[stage.status]}
            </span>
            <span className="node-label">
              <span className="lane-tag">{lane}</span>
              {label}
            </span>
            <span className="node-time mono">
              {stage.status === 'skipped'
                ? 'skipped'
                : live !== null
                  ? formatMs(live)
                  : stage.ms !== null
                    ? formatMs(stage.ms)
                    : ''}
            </span>
          </div>
        )
      })}
    </div>
  )
}

const ICON: Record<Stage['status'], string> = {
  pending: '○',
  running: '◐',
  done: '✓',
  skipped: '–',
}

function ModelConsole({ trace, now }: { trace: ReviewState; now: number }) {
  const hasDraft = trace.output.draft.length > 0 || trace.stages.drafting.status === 'running'
  const [tabPref, setTab] = useState<ModelCall | null>(null)
  const tab: ModelCall = tabPref ?? (hasDraft ? 'draft' : 'extract')
  const call = trace.calls[tab]
  const text = trace.output[tab]
  const streaming = trace.running && call !== undefined && call.ms === null
  const bodyRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    const body = bodyRef.current
    if (body && streaming) body.scrollTop = body.scrollHeight
  }, [text, streaming])

  const callElapsed =
    call && trace.clockStart !== null
      ? call.ms ?? (trace.running ? now - trace.clockStart - call.startT : null)
      : null

  return (
    <div className="console-wrap">
      <div className="row-between">
        <p className="eyebrow">Model output</p>
        <div className="tabs" role="tablist">
          {(['extract', 'draft'] as ModelCall[]).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              disabled={name === 'draft' && !hasDraft}
              onClick={() => setTab(name)}
            >
              {name === 'extract' ? 'Extract' : 'Draft'}
            </button>
          ))}
        </div>
      </div>
      <p className="console-meta mono">
        {call ? (
          <>
            {call.replay ? 'recorded reply' : streaming ? 'streaming from mlx_lm' : 'mlx_lm reply'} ·{' '}
            {text.length.toLocaleString()} chars
            {call.tokens !== null && ` · ${call.tokens.toLocaleString()} tokens`}
            {callElapsed !== null && ` · ${formatMs(callElapsed)}`}
          </>
        ) : tab === 'draft' ? (
          'The model phrases redlines only after Python has decided the verdicts.'
        ) : (
          'Waiting for the extraction call.'
        )}
      </p>
      <pre ref={bodyRef} className={streaming ? 'console streaming' : 'console'}>
        {text ||
          (streaming
            ? 'Reading the contract. The first token comes after the model has read the whole prompt…'
            : ' ')}
      </pre>
      <p className="faint console-note">
        {tab === 'extract'
          ? 'The model returns quotes and fields only. It has no field for green, yellow, or red.'
          : 'Comments are prose. They cannot change a verdict or the route.'}
      </p>
    </div>
  )
}

function Checks({ trace }: { trace: ReviewState }) {
  const positions = trace.started?.positions ?? []
  if (trace.documentType === 'other') {
    return (
      <div className="checks">
        <p className="eyebrow">Citation gate and rules</p>
        <p className="muted">The model classified this as not an NDA. No playbook position is scored.</p>
      </div>
    )
  }
  return (
    <div className="checks">
      <p className="eyebrow">Citation gate and rules</p>
      <div className="checks-scroll">
        <table className="table checks-table">
          <thead>
            <tr>
              <th>Position</th>
              <th>Quote in contract?</th>
              <th>Python rule</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((spec) => {
              const citation = trace.citations[spec.id]
              const rule = trace.rules[spec.id]
              const comment = trace.comments[spec.id]
              return (
                <tr key={spec.id} className={rule ? 'reveal' : 'waiting'}>
                  <td>
                    <div>{spec.title}</div>
                    <div className="mono faint">{spec.critical ? 'critical' : 'standard'}</div>
                  </td>
                  <td>
                    {!citation ? (
                      <span className="faint">…</span>
                    ) : !citation.present ? (
                      <span className="gate absent">absent</span>
                    ) : citation.found ? (
                      <span className="gate ok" title={citation.excerpt ?? undefined}>
                        ✓ verbatim
                      </span>
                    ) : (
                      <span className="gate bad" title={citation.excerpt ?? undefined}>
                        ✗ not found
                      </span>
                    )}
                  </td>
                  <td className="mono rule-cell">{rule ? ruleCall(rule) : <span className="faint">…</span>}</td>
                  <td>
                    {rule ? <span className={`route ${tone(rule.verdict)}`}>{rule.verdict}</span> : null}
                    {comment && (
                      <div className="mono faint nowrap" title={comment.text}>
                        ✎ {comment.source}
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Router({ trace }: { trace: ReviewState }) {
  const route = trace.route
  return (
    <div className="router">
      <p className="eyebrow">Router</p>
      <div className="router-row">
        {VERDICTS.map((verdict) => (
          <span key={verdict} className={`tally ${tone(verdict)}`}>
            {verdict} <strong>{route?.tally[verdict] ?? 0}</strong>
          </span>
        ))}
        <span className="router-arrow" aria-hidden="true">
          →
        </span>
        {route ? <RouteChip route={route.route} /> : <span className="faint">waiting</span>}
      </div>
      <p className="faint" style={{ margin: 0 }}>
        Critical reject or ungrounded → red. Any fallback or standard reject → yellow. Otherwise
        green. Plain Python, no model.
      </p>
    </div>
  )
}

function ruleCall(rule: RuleEvent): string {
  if (rule.basis === 'absent') return 'absent → playbook if_absent'
  if (rule.basis === 'ungrounded') return 'blocked by citation gate'
  return `${rule.rule}(${formatFields(rule.fields)})`
}

function formatFields(fields: Fields): string {
  return Object.entries(fields)
    .map(([key, value]) => `${key}=${typeof value === 'string' ? `"${value}"` : String(value)}`)
    .join(', ')
}

function tone(verdict: Verdict): string {
  if (verdict === 'accept') return 'green'
  if (verdict === 'fallback') return 'yellow'
  return 'red'
}

function shortModel(model: string | undefined): string {
  if (!model) return 'model'
  return model.split('/').pop() ?? model
}

function formatMs(ms: number): string {
  if (ms < 1) return '<1 ms'
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${Math.round(seconds % 60)}s`
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), 200)
    return () => window.clearInterval(id)
  }, [active])
  return now
}
