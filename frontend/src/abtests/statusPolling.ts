import { ApiClientError } from '../auth/http.ts'
import type { ABTestJob } from './types.ts'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

export const STATUS_POLL_MS = 5_000

export interface StatusPollingSnapshot {
  job: ABTestJob | null
  paused: boolean
  error: string | null
  fatal: boolean
}

/** 结构化最小接口：任何提供状态查询的客户端都可复用本会话。 */
export interface StatusPollingClient {
  get(testId: string, signal?: AbortSignal): Promise<ABTestJob>
}

export interface StatusPollingSession {
  /** 执行一轮状态读取；重复调用在在途请求未结算时复用同一 Promise。 */
  tick(): Promise<void>
  dispose(): void
}

/** 403/404 属权限或资源终止，轮询应停止；其余（5xx、断网等）视为暂时性故障。 */
export function isNonRetryableFailure(cause: unknown): boolean {
  return (
    cause instanceof ApiClientError && [403, 404].includes(cause.status ?? 0)
  )
}

function failureMessage(cause: unknown): string | null {
  return cause instanceof Error ? cause.message : null
}

function defaultSchedule(callback: () => void, ms: number): () => void {
  const timer = setTimeout(callback, ms)
  return () => clearTimeout(timer)
}

/** AB 测试状态轮询的框架无关会话：终态或 403/404 停止；
 * 暂时性故障保留旧快照、可见错误并继续按固定间隔重试；
 * dispose 即中止在途请求、取消已排定的下一轮并静默丢弃迟到结果。
 * 由 useStatusPolling 适配为 Hook，快照按调用方的 (testId, attempt) 守卫。
 */
export function createStatusPollingSession(options: {
  client: StatusPollingClient
  testId: string
  schedule?: (callback: () => void, ms: number) => () => void
  onUpdate: (snapshot: StatusPollingSnapshot) => void
}): StatusPollingSession {
  const { client, testId, onUpdate } = options
  const schedule = options.schedule ?? defaultSchedule
  const controller = new AbortController()
  let disposed = false
  let paused = false
  let cancelTimer: (() => void) | null = null
  let inFlight: Promise<void> | null = null
  let latest: StatusPollingSnapshot = {
    job: null,
    paused: false,
    error: null,
    fatal: false,
  }

  function emit(update: Partial<StatusPollingSnapshot>): void {
    latest = { ...latest, ...update }
    onUpdate(latest)
  }

  function stopTimer(): void {
    if (cancelTimer !== null) {
      cancelTimer()
      cancelTimer = null
    }
  }

  async function runTick(): Promise<void> {
    if (disposed || paused || controller.signal.aborted) return
    try {
      const job = await client.get(testId, controller.signal)
      if (disposed || controller.signal.aborted) return
      if (TERMINAL.has(job.status)) {
        paused = true
        emit({ job, paused: true, error: null, fatal: false })
        return
      }
      emit({ job, paused: false, error: null, fatal: false })
      cancelTimer = schedule(() => {
        cancelTimer = null
        void tick()
      }, STATUS_POLL_MS)
    } catch (cause) {
      if (disposed || controller.signal.aborted) return
      if (isNonRetryableFailure(cause)) {
        paused = true
        emit({
          paused: true,
          error: failureMessage(cause),
          fatal: true,
        })
        return
      }
      emit({ error: failureMessage(cause), fatal: false })
      cancelTimer = schedule(() => {
        cancelTimer = null
        void tick()
      }, STATUS_POLL_MS)
    }
  }

  function tick(): Promise<void> {
    if (inFlight) return inFlight
    inFlight = runTick().finally(() => {
      inFlight = null
    })
    return inFlight
  }

  function dispose(): void {
    disposed = true
    stopTimer()
    controller.abort()
  }

  return { tick, dispose }
}
