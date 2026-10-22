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

export type ObserverMode = 'idle' | 'connecting' | 'live' | 'degraded' | 'stopped'

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

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'paused'])

export function isSettledStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status)
}

export function resolveProgressWsUrl(
  url: string,
  loc: { protocol: string; host: string },
): string {
  void url
  void loc
  throw new Error('not implemented')
}

export function createProgressObserver(deps: ObserverDeps): ProgressObserver {
  void deps
  throw new Error('not implemented')
}
