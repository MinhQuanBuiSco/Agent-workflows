export type Verdict = 'accept' | 'fallback' | 'reject' | 'ungrounded'
export type RouteName = 'green' | 'yellow' | 'red' | 'out_of_playbook'
export type MatterStatus = 'new' | 'running' | 'needs_review' | 'approved'
export type ReviewMode = 'fixture' | 'live'

export interface Position {
  id: string
  title: string
  critical: boolean
  verdict: Verdict
  model_verdict: Verdict
  present: boolean
  excerpt: string | null
  citation_ok: boolean | null
  rationale: string
  comment: string | null
  fields: Record<string, string | number | boolean | null>
  overridden: boolean
  human_note: string | null
}

export interface AuditEvent {
  id: string
  at: string
  actor: string
  kind: string
  detail: string
}

export interface Matter {
  id: string
  filename: string
  sample_id: string | null
  title: string
  counterparty: string | null
  status: MatterStatus
  document_type: string | null
  route: RouteName | null
  model_route: RouteName | null
  route_reasons: string[]
  disposition: 'approved' | 'approved_with_exceptions' | null
  positions: Position[]
  text: string
  audit: AuditEvent[]
  created_at: string
}

export interface MatterSummary {
  id: string
  filename: string
  sample_id: string | null
  title: string
  counterparty: string | null
  status: MatterStatus
  document_type: string | null
  route: RouteName | null
  model_route: RouteName | null
  disposition: 'approved' | 'approved_with_exceptions' | null
  created_at: string
}

export interface Sample {
  id: string
  title: string
  counterparty: string
  summary: string
  document_type: 'nda' | 'other'
}

export interface PlaybookPosition {
  id: string
  title: string
  critical: boolean
  if_absent: Verdict | 'accept' | 'fallback' | 'reject'
  rule: string
  requirement: string
  fallback_comment: string
}

export interface Playbook {
  id: string
  name: string
  company: string
  positions: PlaybookPosition[]
}

export interface EvalRow {
  id: string
  title: string
  gold_route: RouteName
  predicted_route: RouteName
  false_green: boolean
  route_match: boolean
  citation_failures: number
  false_accepts: number
}

export interface EvalReport {
  mode: ReviewMode
  sample_count: number
  false_green: number
  false_green_rate: number
  route_correct: number
  route_accuracy: number
  false_accept: number
  false_accept_base: number
  citation_failures: number
  rows: EvalRow[]
  error: string | null
}

export interface EvalBundle {
  fixture: EvalReport
  live: EvalReport | null
}

export interface LlmStatus {
  reachable: boolean
  base_url: string
  model: string
  served_models: string[]
  detail?: string
}

export type ProgressStep =
  | 'parsing'
  | 'extracting'
  | 'verifying'
  | 'adjudicating'
  | 'drafting'
  | 'routing'

export type Lane = 'model' | 'python'
export type StageStatus = 'pending' | 'running' | 'done' | 'skipped'
export type ModelCall = 'extract' | 'draft'
export type Fields = Record<string, string | number | boolean | null>

interface Stamped {
  seq: number
  t: number
}

export interface RunStartedEvent extends Stamped {
  type: 'run_started'
  mode: ReviewMode
  model: string
  positions: { id: string; title: string; critical: boolean; rule: string }[]
}

export interface ProgressEvent extends Stamped {
  type: 'progress'
  step: ProgressStep
  lane: Lane
  status: Exclude<StageStatus, 'pending'>
  message: string
  ms: number | null
}

export interface ModelCallEvent extends Stamped {
  type: 'model_call'
  call: ModelCall
  status: 'start' | 'end'
  replay: boolean
  prompt_chars?: number | null
  tokens?: number | null
  ms?: number
}

export interface CitationEvent extends Stamped {
  type: 'citation'
  position: string
  title: string
  present: boolean
  excerpt: string | null
  found: boolean | null
}

export interface RuleEvent extends Stamped {
  type: 'rule'
  position: string
  title: string
  rule: string | null
  basis: 'rule' | 'absent' | 'ungrounded'
  fields: Fields
  verdict: Verdict
  rationale: string
  critical: boolean
}

export interface CommentEvent extends Stamped {
  type: 'comment'
  position: string
  title: string
  text: string
  source: 'model' | 'playbook'
}

export interface RouteEvent extends Stamped {
  type: 'route'
  route: RouteName
  reasons: string[]
  tally: Partial<Record<Verdict, number>>
}

export type StreamEvent =
  | RunStartedEvent
  | ProgressEvent
  | ModelCallEvent
  | CitationEvent
  | RuleEvent
  | CommentEvent
  | RouteEvent
  | (Stamped & { type: 'model_delta'; call: ModelCall; text: string })
  | (Stamped & { type: 'model_retry'; call: ModelCall; error: string })
  | (Stamped & { type: 'document'; document_type: 'nda' | 'other'; counterparty: string | null })
  | (Stamped & { type: 'result'; data: Matter })
  | (Stamped & { type: 'error'; message: string })
  | { type: 'keepalive' }
  | { type: 'clock'; t: number; done: boolean }
