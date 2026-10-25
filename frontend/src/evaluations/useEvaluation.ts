import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../auth/http.ts'
import { readViteEnv } from '../config/env.ts'
import {
  createProgressObserver,
  resolveProgressWsUrl,
  type ProgressObserver,
} from './observer.ts'
import type { EvaluationSnapshot, EvaluationClient } from './types.ts'

type SnapshotLoader = (
  id: string,
  signal: AbortSignal,
) => Promise<EvaluationSnapshot>

export function useEvaluation(
  client: EvaluationClient,
  evaluationId: string,
  owner: string | null,
  fetchSnapshot?: SnapshotLoader,
) {
  const load = fetchSnapshot ?? client.get
  const [attempt, setAttempt] = useState(0)
  const generation = useRef(0)
  const [snapshot, setSnapshot] = useState<{
    client: EvaluationClient
    evaluationId: string
    owner: string
    attempt: number
    load: SnapshotLoader
    data?: EvaluationSnapshot
    error?: string
  }>()
  const reload = useCallback(() => setAttempt((value) => value + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    const operation = ++generation.current
    if (owner && evaluationId) {
      const identity = { client, load, owner, evaluationId, attempt }
      void load(evaluationId, controller.signal).then(
        (data) => {
          if (!controller.signal.aborted && generation.current === operation)
            setSnapshot({ ...identity, data })
        },
        (error: unknown) => {
          if (controller.signal.aborted || generation.current !== operation)
            return
          const denied =
            error instanceof ApiClientError &&
            [403, 404].includes(error.status ?? 0)
          setSnapshot((previous) => ({
            ...identity,
            data:
              !denied &&
              previous?.client === client &&
              previous.load === load &&
              previous.owner === owner &&
              previous.evaluationId === evaluationId
                ? previous.data
                : undefined,
            error:
              error instanceof ApiClientError && error.message
                ? error.message
                : '加载任务失败，请重试',
          }))
        },
      )
    }
    return () => controller.abort()
  }, [client, load, evaluationId, owner, attempt])
  const current =
    !!owner &&
    snapshot?.owner === owner &&
    snapshot.client === client &&
    snapshot.load === load &&
    snapshot.evaluationId === evaluationId
  const loading = !current || snapshot.attempt !== attempt
  return {
    data: current ? snapshot.data : undefined,
    error: current && !loading ? snapshot.error : undefined,
    loading,
    reload,
  }
}

const LIVE_ACTIVE_STATUSES = new Set(['pending', 'running', 'paused'])

export function isLiveStatus(status: string): boolean {
  return LIVE_ACTIVE_STATUSES.has(status)
}

export interface EvaluationLive {
  /** 观察器经 HTTP 真值刷新的最新评估（无快照时为 null，回退一次性抓取） */
  evaluation: EvaluationSnapshot | null
  /** 观察器通道模式：live=WS 已订阅；degraded=降级轮询；connecting/stopped */
  mode: string
  /** 会话失效（401/4401 恢复失败）：页面应清会话回跳登录 */
  unauthorized: boolean
  forbidden: boolean
  error: string | null
  /** 手动触发一次观察器刷新（等价页面「刷新任务」） */
  refresh: () => void
  runMutation: (fn: () => Promise<void>) => Promise<void>
}

/** 步骤 4（issue #225）：把进度观察器接入 React。
 *
 * enabled（评估处于非终态）时挂载观察器：原生 WebSocket 仅在此适配器创建
 * （Cookie 认证，token 不进 URL）；HTTP 快照经 client.get 走既有 401 刷新。
 * 页面可见性/网络状态变化映射为观察器的暂停/恢复。
 */
export function useEvaluationLive(
  client: EvaluationClient,
  evaluationId: string,
  owner: string | null,
  enabled: boolean,
  fetchSnapshot?: SnapshotLoader,
): EvaluationLive {
  const load = fetchSnapshot ?? client.get
  const [snapshot, setSnapshot] = useState<{
    client: EvaluationClient | null
    load: SnapshotLoader | null
    owner: string | null
    evaluationId: string
    evaluation: EvaluationSnapshot | null
    mode: string
    unauthorized: boolean
    forbidden: boolean
    error: string | null
  }>({
    client: null,
    load: null,
    owner: null,
    evaluationId: '',
    evaluation: null,
    mode: 'idle',
    unauthorized: false,
    forbidden: false,
    error: null,
  })
  const observerRef = useRef<ProgressObserver | null>(null)

  useEffect(() => {
    // 观察器实例在 effect 内创建（含 readViteEnv 等非纯读取），render 保持纯函数；
    // 换代时旧实例由 cleanup dispose，遗留 snapshot 由 aligned 派生守卫拦截。
    observerRef.current = null
    if (!enabled || !client) return
    const instance = createProgressObserver({
      fetchSnapshot: load,
      connectSocket: (handlers) => {
        try {
          const env = readViteEnv()
          const url = resolveProgressWsUrl(env.wsUrl, {
            protocol: window.location.protocol,
            host: window.location.host,
          })
          const ws = new WebSocket(url)
          ws.onopen = () => handlers.onOpen()
          ws.onmessage = (event) => {
            let frame: unknown
            try {
              frame = JSON.parse(String(event.data))
            } catch {
              return // 非 JSON 帧忽略；服务端对畸形帧同样忽略
            }
            // 解析与分发分离：处理器的异常不应被当作畸形帧吞掉
            handlers.onMessage(
              frame as Parameters<typeof handlers.onMessage>[0],
            )
          }
          ws.onclose = (event) => handlers.onClose(event.code)
          ws.onerror = () => handlers.onError()
          return {
            send: (frame) => ws.send(JSON.stringify(frame)),
            close: (code) => ws.close(code),
          }
        } catch {
          // URL 非法等同步构造失败：走观察器失败路径（降级轮询），不击穿页面
          handlers.onError()
          return {
            send: () => undefined,
            close: () => undefined,
          }
        }
      },
      clock: {
        now: () => Date.now(),
        setTimeout: (fn, ms) => setTimeout(fn, ms),
        clearTimeout: (handle) =>
          clearTimeout(handle as ReturnType<typeof setTimeout>),
      },
      onChange: (event) => {
        // 关键：接受事件时必须以当前代身份盖章写入——snapshot 初始无身份，
        // 只比对不盖章会让 aligned 守卫永久拦截所有事件（复审 P0 教训）。
        setSnapshot((previous) => {
          const alignedPrevious =
            previous.client === client &&
            previous.load === load &&
            previous.owner === owner &&
            previous.evaluationId === evaluationId
              ? previous
              : {
                  client,
                  load,
                  owner,
                  evaluationId,
                  evaluation: null,
                  mode: 'idle',
                  unauthorized: false,
                  forbidden: false,
                  error: null,
                }
          if (event.type === 'snapshot')
            return {
              ...alignedPrevious,
              evaluation: event.evaluation,
              mode: event.mode,
              forbidden: false,
              error: null,
            }
          if (event.type === 'mode')
            return { ...alignedPrevious, mode: event.mode }
          if (event.type === 'forbidden')
            return {
              ...alignedPrevious,
              evaluation: null,
              forbidden: true,
              error: null,
            }
          if (event.type === 'error')
            return { ...alignedPrevious, error: '实时数据暂时无法更新，请重试' }
          if (event.type === 'unauthorized')
            return { ...alignedPrevious, evaluation: null, unauthorized: true }
          return alignedPrevious
        })
      },
      recoverSession: async () => {
        // 401 到达观察器时 HTTP 层已完成一次刷新重试；这里再探测一次：
        // 成功说明会话仍有效，仍 401 则判定失效。
        try {
          await client.get(evaluationId)
          return true
        } catch {
          return false
        }
      },
    })
    observerRef.current = instance
    instance.start(evaluationId)
    return () => {
      instance.dispose()
      observerRef.current = null
    }
  }, [client, load, evaluationId, owner, enabled])

  // 页面可见性 / 网络状态 → 观察器暂停与恢复
  useEffect(() => {
    if (!enabled) return
    const sync = () => {
      const current = observerRef.current
      if (!current) return
      current.setVisible(document.visibilityState !== 'hidden')
      current.setOnline(navigator.onLine)
    }
    document.addEventListener('visibilitychange', sync)
    window.addEventListener('online', sync)
    window.addEventListener('offline', sync)
    sync()
    return () => {
      document.removeEventListener('visibilitychange', sync)
      window.removeEventListener('online', sync)
      window.removeEventListener('offline', sync)
    }
  }, [enabled, observerRef])

  const aligned =
    !!owner &&
    snapshot.client === client &&
    snapshot.load === load &&
    snapshot.owner === owner &&
    snapshot.evaluationId === evaluationId
  useEffect(() => {
    // A stopped observer may return an active HTTP snapshot after an explicit
    // permission retry. Resume only after that successful read; paused/terminal
    // snapshots and denied resources must stay stopped.
    if (
      aligned &&
      enabled &&
      snapshot.mode === 'stopped' &&
      !snapshot.forbidden &&
      !snapshot.unauthorized &&
      snapshot.evaluation &&
      ['pending', 'running'].includes(snapshot.evaluation.status)
    )
      observerRef.current?.start(evaluationId)
  }, [aligned, enabled, evaluationId, snapshot])
  const refresh = useCallback(() => observerRef.current?.refresh(), [])
  const runMutation = useCallback(async (fn: () => Promise<void>) => {
    const observer = observerRef.current
    if (observer) await observer.runMutation(fn)
    else await fn()
  }, [])
  return {
    evaluation: aligned && enabled ? snapshot.evaluation : null,
    mode: aligned && enabled ? snapshot.mode : 'idle',
    unauthorized: aligned ? snapshot.unauthorized : false,
    forbidden: aligned && enabled ? snapshot.forbidden : false,
    error: aligned && enabled ? snapshot.error : null,
    refresh,
    runMutation,
  }
}
