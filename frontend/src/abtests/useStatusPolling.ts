import { useEffect, useRef, useState } from 'react'
import type { ABTestClient, ABTestJob } from './types.ts'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
const POLL_MS = 5_000

export interface StatusPollingState {
  job: ABTestJob | null
  paused: boolean
  reload: () => void
}

interface StatusSnapshot {
  testId: string | null
  attempt: number
  job: ABTestJob | null
  paused: boolean
}

/** AB 测试状态轮询：进程内线程执行，无 task 通道，只能轮询测试状态（5s）。
 * 终态停止；单次失败不打断（下一周期自然重试）。状态按快照派生，
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
  })
  const generation = useRef(0)

  useEffect(() => {
    if (!testId) return
    const controller = new AbortController()
    const operation = ++generation.current
    let timer: ReturnType<typeof setTimeout> | null = null
    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    }
    const patch = (update: Partial<StatusSnapshot>): void => {
      if (controller.signal.aborted || operation !== generation.current) return
      setSnapshot((previous) => ({ ...previous, testId, attempt, ...update }))
    }
    const tick = async (): Promise<void> => {
      if (controller.signal.aborted || operation !== generation.current) return
      try {
        const job = await client.get(testId, controller.signal)
        if (controller.signal.aborted || operation !== generation.current)
          return
        patch({ job })
        if (TERMINAL.has(job.status)) {
          clearTimer()
          patch({ paused: true })
          return
        }
        timer = setTimeout(() => void tick(), POLL_MS)
      } catch {
        if (controller.signal.aborted || operation !== generation.current)
          return
        // 单次失败不打断轮询，下一周期自然重试
        timer = setTimeout(() => void tick(), POLL_MS)
      }
    }
    void tick()
    return () => {
      controller.abort()
      clearTimer()
    }
  }, [client, testId, attempt])
  const current = snapshot.testId === testId && snapshot.attempt === attempt
  return {
    job: current ? snapshot.job : null,
    paused: current ? snapshot.paused : false,
    reload: () => setAttempt((value) => value + 1),
  }
}
