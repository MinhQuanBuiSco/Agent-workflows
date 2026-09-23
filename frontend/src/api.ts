import type {
  EvalBundle,
  EvalReport,
  LlmStatus,
  Matter,
  MatterSummary,
  Playbook,
  ReviewMode,
  Sample,
  StreamEvent,
  Verdict,
} from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function readError(response: Response): Promise<ApiError> {
  let detail = response.statusText || 'Request failed'
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    // A non-JSON error body still surfaces as the status text.
  }
  return new ApiError(response.status, detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw await readError(response)
  return (await response.json()) as T
}

export function getSamples() {
  return request<Sample[]>('/api/samples')
}

export function getMatters() {
  return request<MatterSummary[]>('/api/matters')
}

export function getMatter(id: string) {
  return request<Matter>(`/api/matters/${id}`)
}

export function openSample(id: string) {
  return request<Matter>(`/api/matters/sample/${id}`, { method: 'POST' })
}

export function uploadContract(file: File) {
  const body = new FormData()
  body.append('file', file)
  return request<Matter>('/api/matters', { method: 'POST', body })
}

export function openDemo() {
  return request<Matter>('/api/matters/demo', { method: 'POST' })
}

export const DEMO_PDF_URL = '/api/demo.pdf'

export function getPlaybook() {
  return request<Playbook>('/api/playbook')
}

export function getLlm() {
  return request<LlmStatus>('/api/llm')
}

export function getEvals() {
  return request<EvalBundle>('/api/evals')
}

export function runEval(mode: ReviewMode) {
  return request<EvalReport>(`/api/evals/run?mode=${mode}`, { method: 'POST' })
}

export function decide(
  id: string,
  body: {
    action: 'override' | 'approve' | 'approve_with_exceptions'
    overrides?: { position_id: string; verdict: Verdict; note: string }[]
    note?: string
  },
) {
  return request<Matter>(`/api/matters/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function streamReview(
  id: string,
  mode: ReviewMode,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/matters/${id}/review?mode=${mode}`, {
    method: 'POST',
    signal,
  })
  await readStream(response, onEvent)
}

/** Replay a matter's last review trace, then follow it while it runs. False if none. */
export async function followReview(
  id: string,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<boolean> {
  const response = await fetch(`/api/matters/${id}/events`, { signal })
  if (response.status === 404) return false
  await readStream(response, onEvent)
  return true
}

async function readStream(response: Response, onEvent: (event: StreamEvent) => void) {
  if (!response.ok) throw await readError(response)
  if (!response.body) throw new ApiError(500, 'Review returned an empty stream.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (!data) continue
      onEvent(JSON.parse(data) as StreamEvent)
    }
  }
}
