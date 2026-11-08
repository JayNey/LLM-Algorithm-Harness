import { useEffect, useRef, useState } from 'react'
import {
  createStatusPollingSession,
  type StatusPollingSnapshot,
} from './statusPolling.ts'
import type { ABTestClient, ABTestJob } from './types.ts'

export interface StatusPollingState {
  job: ABTestJob | null
  paused: boolean
  error: string | null
  fatal: boolean
  reload: () => void
}

interface StatusSnapshot extends StatusPollingSnapshot {
  testId: string | null
  attempt: number
}

/** AB 测试状态轮询：进程内线程执行，无 task 通道，只能轮询测试状态（5s）。
 * 终态与 403/404 停止；暂时性故障保留旧快照、可见错误并继续重试。
 * 轮询语义见 statusPolling.ts；快照按 (testId, attempt) 派生，
 * effect 内不做同步 setState（react-hooks/set-state-in-effect）。
 */
export function useStatusPolling(
  client: ABTestClient,
  testId: string | null,
): StatusPollingState {
  const [attempt, setAttempt] = useState(0)
  const [snapshot, setSnapshot] = useState<StatusSnapshot>({
    testId: null,
    attempt: 0,
    job: null,
    paused: false,
    error: null,
    fatal: false,
  })
  const generation = useRef(0)

  useEffect(() => {
    if (!testId) return
    const operation = ++generation.current
    const session = createStatusPollingSession({
      client,
      testId,
      onUpdate: (update) => {
        if (operation !== generation.current) return
        setSnapshot((previous) => ({ ...previous, testId, attempt, ...update }))
      },
    })
    void session.tick()
    return () => session.dispose()
  }, [client, testId, attempt])
  const current = snapshot.testId === testId && snapshot.attempt === attempt
  return {
    job: current ? snapshot.job : null,
    paused: current ? snapshot.paused : false,
    error: current ? snapshot.error : null,
    fatal: current ? snapshot.fatal : false,
    reload: () => setAttempt((value) => value + 1),
  }
}
