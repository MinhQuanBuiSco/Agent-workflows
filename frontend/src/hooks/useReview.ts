import { useCallback, useReducer, useRef } from 'react'
import { followReview, streamReview } from '../api'
import type {
  CitationEvent,
  CommentEvent,
  Lane,
  Matter,
  ModelCall,
  ModelCallEvent,
  ProgressStep,
  ReviewMode,
  RouteEvent,
  RuleEvent,
  RunStartedEvent,
  StageStatus,
  StreamEvent,
} from '../types'

export const STAGES: { step: ProgressStep; lane: Lane; label: string }[] = [
  { step: 'parsing', lane: 'python', label: 'Read' },
  { step: 'extracting', lane: 'model', label: 'Extract' },
  { step: 'verifying', lane: 'python', label: 'Citation gate' },
  { step: 'adjudicating', lane: 'python', label: 'Playbook rules' },
  { step: 'drafting', lane: 'model', label: 'Draft comments' },
  { step: 'routing', lane: 'python', label: 'Route' },
]

export interface Stage {
  status: StageStatus
  message: string
  startT: number | null
  ms: number | null
}

export interface CallState {
  replay: boolean
  startT: number
  /** Known once a live call ends. A replay has none. */
  tokens: number | null
  ms: number | null
}

export interface Trace {
  matterId: string | null
  running: boolean
  started: RunStartedEvent | null
  /** Wall-clock time the run started, so running stages can show a live timer. */
  clockStart: number | null
  lastSeq: number
  lastT: number
  stages: Record<ProgressStep, Stage>
  current: ProgressStep | null
  output: Record<ModelCall, string>
  calls: Partial<Record<ModelCall, CallState>>
  retries: string[]
  documentType: 'nda' | 'other' | null
  citations: Record<string, CitationEvent>
  rules: Record<string, RuleEvent>
  comments: Record<string, CommentEvent>
  route: RouteEvent | null
  result: Matter | null
  error: string | null
}

function emptyStages(): Record<ProgressStep, Stage> {
  return Object.fromEntries(
    STAGES.map(({ step }) => [step, { status: 'pending', message: '', startT: null, ms: null }]),
  ) as Record<ProgressStep, Stage>
}

function initial(matterId: string | null = null, running = false): Trace {
  return {
    matterId,
    running,
    started: null,
    clockStart: null,
    lastSeq: -1,
    lastT: 0,
    stages: emptyStages(),
    current: null,
    output: { extract: '', draft: '' },
    calls: {},
    retries: [],
    documentType: null,
    citations: {},
    rules: {},
    comments: {},
    route: null,
    result: null,
    error: null,
  }
}

type Action =
  | { kind: 'begin'; matterId: string }
  | { kind: 'event'; matterId: string; event: StreamEvent }
  | { kind: 'end'; matterId: string; error?: string }
  | { kind: 'reset' }

function reduce(state: Trace, action: Action): Trace {
  if (action.kind === 'reset') return initial()
  if (action.kind === 'begin') return initial(action.matterId, true)
  if (action.matterId !== state.matterId) return state
  if (action.kind === 'end') {
    return {
      ...state,
      running: false,
      current: null,
      error: action.error ?? state.error,
    }
  }

  const event = action.event
  if (event.type === 'keepalive') return state
  if (event.type === 'clock') {
    // Sent first on every stream, so a late reader's timers match the server's.
    return event.done ? state : { ...state, clockStart: Date.now() - event.t }
  }
  if (event.seq <= state.lastSeq) return state
  const next: Trace = { ...state, lastSeq: event.seq, lastT: event.t }

  switch (event.type) {
    case 'run_started':
      return {
        ...initial(state.matterId, true),
        lastSeq: event.seq,
        started: event,
        lastT: event.t,
        clockStart: state.clockStart ?? Date.now() - event.t,
      }
    case 'progress': {
      const prior = state.stages[event.step]
      next.stages = {
        ...state.stages,
        [event.step]: {
          status: event.status,
          message: event.message,
          startT: event.status === 'running' ? event.t : prior.startT,
          ms: event.ms ?? prior.ms,
        },
      }
      if (event.status === 'running') next.current = event.step
      else if (state.current === event.step) next.current = null
      return next
    }
    case 'model_call':
      next.calls = { ...state.calls, [event.call]: callState(state.calls[event.call], event) }
      return next
    case 'model_delta':
      next.output = { ...state.output, [event.call]: state.output[event.call] + event.text }
      return next
    case 'model_retry':
      next.retries = [...state.retries, event.error]
      next.output = {
        ...state.output,
        [event.call]: `${state.output[event.call]}\n\n── invalid JSON, retrying ──\n\n`,
      }
      return next
    case 'document':
      next.documentType = event.document_type
      return next
    case 'citation':
      next.citations = { ...state.citations, [event.position]: event }
      return next
    case 'rule':
      next.rules = { ...state.rules, [event.position]: event }
      return next
    case 'comment':
      next.comments = { ...state.comments, [event.position]: event }
      return next
    case 'route':
      next.route = event
      return next
    case 'result':
      next.result = event.data
      next.running = false
      next.current = null
      return next
    case 'error':
      next.error = event.message
      next.running = false
      next.current = null
      return next
  }
}

function callState(prior: CallState | undefined, event: ModelCallEvent): CallState {
  if (event.status === 'start') {
    return { replay: event.replay, startT: event.t, tokens: null, ms: null }
  }
  return {
    replay: event.replay,
    startT: prior?.startT ?? event.t,
    tokens: event.tokens ?? null,
    ms: event.ms ?? null,
  }
}

export function useReview() {
  const [state, dispatch] = useReducer(reduce, undefined, () => initial())
  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    abortRef.current?.abort()
    dispatch({ kind: 'reset' })
  }, [])

  const consume = useCallback(
    async (matterId: string, open: (signal: AbortSignal, onEvent: (e: StreamEvent) => void) => Promise<unknown>) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      dispatch({ kind: 'begin', matterId })
      try {
        const found = await open(controller.signal, (event) => dispatch({ kind: 'event', matterId, event }))
        if (found === false) dispatch({ kind: 'reset' })
        else dispatch({ kind: 'end', matterId })
      } catch (error) {
        // Leaving the page aborts the reader only. The review keeps running on the server.
        if ((error as Error).name === 'AbortError') return
        dispatch({
          kind: 'end',
          matterId,
          error: error instanceof Error ? error.message : 'Review failed',
        })
      }
    },
    [],
  )

  const run = useCallback(
    (matterId: string, mode: ReviewMode) =>
      consume(matterId, (signal, onEvent) => streamReview(matterId, mode, onEvent, signal)),
    [consume],
  )

  /** Load the trace of the last review, and keep following it if it is still running. */
  const attach = useCallback(
    (matterId: string) =>
      consume(matterId, (signal, onEvent) => followReview(matterId, onEvent, signal)),
    [consume],
  )

  return { ...state, run, attach, reset }
}

export type ReviewState = ReturnType<typeof useReview>
