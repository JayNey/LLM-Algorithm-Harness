/** 评估进度观察器（issue #225 T10，Step 1–3）。
 *
 * WebSocket 订阅为主通道、HTTP 快照为唯一真值：服务端事件只触发失效，
 * 失效在合并窗口内收敛为至多一次刷新。依赖全部注入，原生 WebSocket
 * 仅在 React 适配器中创建；本模块不 import axios 与任何 IO。
 * 时序语义见 openspec/changes/evaluation-observer/design.md。
 */

import type { Evaluation } from './types.ts'

export const OBSERVER_TIMING = {
  subscribeTimeoutMs: 5_000,
  mergeWindowMs: 2_000,
  staleLiveMs: 15_000,
  degradedPollMs: 3_000,
  reconnectBackoffMs: [3_000, 6_000, 12_000, 30_000],
  maxReconnects: 5,
  rateLimitMs: 30_000,
} as const

export type ObserverMode =
  'idle' | 'connecting' | 'live' | 'degraded' | 'stopped'

export type ClientFrame =
  | { action: 'subscribe'; task_id: string }
  | { action: 'unsubscribe'; task_id: string }
  | { action: 'ping' }

export type ServerFrame = { type: string; task_id?: string; data?: unknown }

export interface SocketHandlers {
  onOpen(): void
  onMessage(frame: ServerFrame): void
  onClose(code: number): void
  onError(): void
}

export interface SocketHandle {
  send(frame: ClientFrame): void
  close(code?: number): void
}

export type ObserverEvent =
  | { type: 'snapshot'; evaluation: Evaluation; mode: ObserverMode }
  | { type: 'mode'; mode: ObserverMode }
  | { type: 'error'; message: string; mode: ObserverMode }
  | { type: 'forbidden' }
  | { type: 'unauthorized' }
  | { type: 'settled'; evaluation: Evaluation }

export interface ObserverClock {
  now(): number
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
}

export interface ObserverDeps {
  fetchSnapshot(evaluationId: string, signal: AbortSignal): Promise<Evaluation>
  connectSocket(handlers: SocketHandlers): SocketHandle
  clock: ObserverClock
  onChange(event: ObserverEvent): void
  recoverSession(): Promise<boolean>
}

export interface ProgressObserver {
  start(evaluationId: string): void
  refresh(): void
  invalidate(): void
  setVisible(visible: boolean): void
  setOnline(online: boolean): void
  runMutation(fn: () => Promise<void>): Promise<void>
  dispose(): void
}

const TERMINAL_STATUSES = new Set([
  'completed',
  'failed',
  'cancelled',
  'paused',
])

export function isSettledStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status)
}

export function resolveProgressWsUrl(
  url: string,
  loc: { protocol: string; host: string },
): string {
  const resolved = new URL(url, `${loc.protocol}//${loc.host}`)
  if (resolved.protocol === 'http:') resolved.protocol = 'ws:'
  else if (resolved.protocol === 'https:') resolved.protocol = 'wss:'
  return resolved.toString()
}

interface Connection {
  handle: SocketHandle
  open: boolean
  subscribeSent: boolean
  subscribed: boolean
  subscribeTimer: unknown
  closed: boolean
}

interface InFlight {
  controller: AbortController
  epoch: number
}

export function createProgressObserver(deps: ObserverDeps): ProgressObserver {
  const timing = OBSERVER_TIMING
  let disposed = false
  let paused = false
  let evaluationId: string | null = null
  let epoch = 0
  let mode: ObserverMode = 'idle'
  let conn: Connection | null = null
  let connectAttempts = 0
  let pollFailures = 0
  let rateLimitUntil = 0
  let inFlight: InFlight | null = null
  let pendingInvalidation = false
  let mergeTimer: unknown = null
  let staleTimer: unknown = null
  let pollTimer: unknown = null
  let reconnectTimer: unknown = null
  let rateLimitTimer: unknown = null
  let visible = true
  let online = true

  const backoffFor = (failures: number): number =>
    timing.reconnectBackoffMs[
      Math.min(failures - 1, timing.reconnectBackoffMs.length - 1)
    ]

  const running = (): boolean => visible && online && !disposed && !paused

  function emit(event: ObserverEvent): void {
    if (!disposed) deps.onChange(event)
  }

  function setMode(next: ObserverMode): void {
    if (disposed || mode === next) return
    mode = next
    emit({ type: 'mode', mode })
  }

  function clearHandle(handle: unknown): void {
    if (handle !== null && handle !== undefined) deps.clock.clearTimeout(handle)
  }

  function clearTimers(): void {
    for (const timer of [
      mergeTimer,
      staleTimer,
      pollTimer,
      reconnectTimer,
      rateLimitTimer,
    ]) {
      clearHandle(timer)
    }
    mergeTimer = staleTimer = pollTimer = reconnectTimer = rateLimitTimer = null
    if (conn) clearHandle(conn.subscribeTimer)
  }

  function teardownSocket(): void {
    if (!conn) return
    if (conn.subscribed)
      conn.handle.send({ action: 'unsubscribe', task_id: evaluationId ?? '' })
    conn.handle.close(1000)
    conn = null
  }

  function stopObserving(): void {
    if (inFlight) inFlight.controller.abort()
    pendingInvalidation = false
    clearTimers()
    teardownSocket()
  }

  function settleWith(evaluation: Evaluation): void {
    stopObserving()
    emit({ type: 'settled', evaluation })
    setMode('stopped')
  }

  function armStale(): void {
    clearHandle(staleTimer)
    staleTimer = clock_timer(() => {
      staleTimer = null
      requestSnapshot('stale')
    }, timing.staleLiveMs)
  }

  function schedulePoll(delay: number): void {
    clearHandle(pollTimer)
    pollTimer = clock_timer(() => {
      pollTimer = null
      requestSnapshot('poll')
    }, delay)
  }

  // clock_timer 包一层：回调执行前统一过守卫
  function clock_timer(fn: () => void, ms: number): unknown {
    return deps.clock.setTimeout(() => {
      if (disposed || paused) return
      fn()
    }, ms)
  }

  function beginEpoch(): InFlight {
    epoch += 1
    const controller = new AbortController()
    inFlight = { controller, epoch }
    return inFlight
  }

  function requestSnapshot(reason: string): void {
    void reason
    if (disposed || paused || evaluationId === null) return
    if (inFlight) {
      if (inFlight.epoch !== epoch) {
        // 旧纪元请求已作废：中止并丢弃，不阻塞新周期的刷新
        inFlight.controller.abort()
        inFlight = null
      } else {
        pendingInvalidation = true
        return
      }
    }
    const now = deps.clock.now()
    if (now < rateLimitUntil) {
      if (rateLimitTimer === null) {
        rateLimitTimer = clock_timer(() => {
          rateLimitTimer = null
          requestSnapshot(reason)
        }, rateLimitUntil - now)
      }
      return
    }
    const flight = beginEpoch()
    const currentEpoch = flight.epoch
    deps.fetchSnapshot(evaluationId, flight.controller.signal).then(
      (result) => {
        if (inFlight === flight) inFlight = null
        if (
          disposed ||
          paused ||
          currentEpoch !== epoch ||
          flight.controller.signal.aborted
        )
          return
        deliverSnapshot(result)
        if (pendingInvalidation && mode !== 'stopped') {
          pendingInvalidation = false
          requestSnapshot('pending')
        }
      },
      (error: unknown) => {
        if (inFlight === flight) inFlight = null
        if (
          disposed ||
          paused ||
          currentEpoch !== epoch ||
          flight.controller.signal.aborted
        )
          return
        handleFetchError(error)
      },
    )
  }

  function deliverSnapshot(result: Evaluation): void {
    emit({ type: 'snapshot', evaluation: result, mode })
    if (isSettledStatus(result.status)) {
      settleWith(result)
      return
    }
    if (mode === 'live') {
      armStale()
    } else if (mode === 'degraded') {
      pollFailures = 0
      schedulePoll(timing.degradedPollMs)
    }
  }

  function handleFetchError(error: unknown): void {
    const status = (error as { status?: number } | null)?.status
    if (status === 403 || status === 404) {
      stopObserving()
      emit({ type: 'forbidden' })
      setMode('stopped')
      return
    }
    if (status === 401) {
      void handleUnauthorized()
      return
    }
    if (status === 429) {
      rateLimitUntil = deps.clock.now() + timing.rateLimitMs
      emit({ type: 'error', message: 'rate limited', mode })
      if (rateLimitTimer === null) {
        rateLimitTimer = clock_timer(() => {
          rateLimitTimer = null
          requestSnapshot('rate-limit-retry')
        }, timing.rateLimitMs)
      }
      return
    }
    const message = error instanceof Error ? error.message : 'snapshot failed'
    emit({ type: 'error', message, mode })
    if (mode === 'degraded') {
      pollFailures += 1
      schedulePoll(backoffFor(pollFailures + 1))
    } else if (mode === 'live') {
      armStale()
    }
  }

  async function handleUnauthorized(): Promise<void> {
    stopObserving()
    const recovered = await deps.recoverSession()
    if (disposed || paused) return
    if (recovered) {
      setMode('connecting')
      requestSnapshot('recover')
      connect()
    } else {
      emit({ type: 'unauthorized' })
      setMode('stopped')
    }
  }

  function invalidate(): void {
    if (disposed || paused || evaluationId === null) return
    if (mergeTimer !== null) return
    mergeTimer = clock_timer(() => {
      mergeTimer = null
      requestSnapshot('merge')
    }, timing.mergeWindowMs)
  }

  function connect(): void {
    if (disposed || paused || evaluationId === null || conn) return
    // 仅首次启动展示 connecting；重连尝试保持 degraded，轮询退避不受影响
    if (mode === 'idle' || mode === 'stopped' || mode === 'live')
      setMode('connecting')
    const target = evaluationId
    const connection: Connection = {
      handle: null as unknown as SocketHandle,
      open: false,
      subscribeSent: false,
      subscribed: false,
      subscribeTimer: null,
      closed: false,
    }
    const isCurrent = (): boolean => conn === connection && !connection.closed
    connection.handle = deps.connectSocket({
      onOpen: () => {
        if (!isCurrent() || connection.open) return
        connection.open = true
        connection.subscribeSent = true
        connection.handle.send({ action: 'subscribe', task_id: target })
        connection.subscribeTimer = clock_timer(() => {
          if (!isCurrent()) return
          connection.closed = true
          conn = null
          connection.handle.close(1000)
          handleSocketFailure('subscribe timeout')
        }, timing.subscribeTimeoutMs)
      },
      onMessage: (frame) => {
        if (!isCurrent()) return
        handleFrame(frame)
      },
      onClose: (code) => {
        if (!isCurrent()) return
        connection.closed = true
        conn = null
        clearHandle(connection.subscribeTimer)
        if (code === 4403) {
          stopObserving()
          emit({ type: 'forbidden' })
          setMode('stopped')
          return
        }
        if (code === 4401) {
          void handleUnauthorized()
          return
        }
        handleSocketFailure(`closed ${code}`)
      },
      onError: () => {
        if (!isCurrent()) return
        connection.closed = true
        conn = null
        clearHandle(connection.subscribeTimer)
        handleSocketFailure('socket error')
      },
    })
    conn = connection
  }

  function handleFrame(frame: ServerFrame): void {
    if (frame.type === 'connected' || frame.type === 'pong') return
    if (frame.type === 'subscribed') {
      if (!conn) return
      clearHandle(conn.subscribeTimer)
      // 进入 live：清掉降级期遗留的轮询周期
      clearHandle(pollTimer)
      pollTimer = null
      conn.subscribed = true
      connectAttempts = 0
      pollFailures = 0
      setMode('live')
      armStale()
      return
    }
    invalidate()
  }

  function handleSocketFailure(reason: string): void {
    connectAttempts += 1
    setMode('degraded')
    // 进入降级：清掉 live 期遗留的兜底定时器
    clearHandle(staleTimer)
    staleTimer = null
    if (connectAttempts >= timing.maxReconnects) {
      // 放弃 WS：保持降级轮询
      if (pollTimer === null) schedulePoll(timing.degradedPollMs)
      emit({ type: 'error', message: reason, mode })
      return
    }
    if (pollTimer === null) schedulePoll(timing.degradedPollMs)
    if (reconnectTimer === null) {
      reconnectTimer = clock_timer(() => {
        reconnectTimer = null
        connect()
      }, backoffFor(connectAttempts))
    }
  }

  function pause(): void {
    paused = true
    if (inFlight) inFlight.controller.abort()
    stopObserving()
  }

  function resumeIfNeeded(): void {
    if (disposed || paused || evaluationId === null) return
    if (mode === 'stopped') return
    connectAttempts = 0
    pollFailures = 0
    requestSnapshot('resume')
    connect()
  }

  return {
    start(id: string): void {
      if (disposed) return
      if (id === evaluationId && mode !== 'idle' && mode !== 'stopped') return
      stopObserving()
      if (inFlight) inFlight.controller.abort()
      evaluationId = id
      epoch += 1
      if (!running()) {
        setMode('idle')
        return
      }
      setMode('connecting')
      requestSnapshot('start')
      connect()
    },
    refresh(): void {
      requestSnapshot('manual')
    },
    invalidate(): void {
      invalidate()
    },
    setVisible(next: boolean): void {
      if (visible === next) return
      visible = next
      if (!visible) pause()
      else {
        paused = false
        resumeIfNeeded()
      }
    },
    setOnline(next: boolean): void {
      if (online === next) return
      online = next
      if (!online) pause()
      else {
        paused = false
        resumeIfNeeded()
      }
    },
    async runMutation(fn: () => Promise<void>): Promise<void> {
      epoch += 1
      if (inFlight) inFlight.controller.abort()
      try {
        await fn()
      } finally {
        if (!disposed) invalidate()
      }
    },
    dispose(): void {
      disposed = true
      if (inFlight) inFlight.controller.abort()
      stopObserving()
      mode = 'stopped'
    },
  }
}
