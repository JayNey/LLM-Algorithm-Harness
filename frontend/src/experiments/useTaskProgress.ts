import { useEffect, useRef, useState } from 'react'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
const POLL_MS = 3_000
const MAX_CONSECUTIVE_FAILURES = 3

/** 结构化最小接口：任何提供 task() 查询的客户端都可复用本 Hook。 */
export interface ProgressPollingClient {
  task(taskId: string, signal?: AbortSignal): Promise<TaskProgressSnapshot>
}
export interface TaskProgressSnapshot {
  status: string
  progress: {
    current: number
    total: number
    percentage: number
    current_step: string
  } | null
  error_message: string | null
}
export interface TaskProgressState<T = TaskProgressSnapshot> {
  task: T | null
  paused: boolean
  reload: () => void
}

interface ProgressSnapshot<T> {
  taskId: string | null
  owner: string | null
  attempt: number
  task: T | null
  paused: boolean
}

/** 轮询实验异步任务进度（实验/基准无 WebSocket，契约见 api/routes/tasks.py）。
 *
 * 终态（completed/failed/cancelled）停止；paused 停止并保留最后进度；
 * 连续失败达到上限暂停并提供手动重试；卸载或参数变化即中止在途请求。
 * 状态按 (taskId, owner, attempt) 快照派生，effect 内不做同步 setState。
 */
export function useTaskProgress<
  T extends TaskProgressSnapshot = TaskProgressSnapshot,
>(
  client: { task(taskId: string, signal?: AbortSignal): Promise<T> },
  taskId: string | null,
  owner: string | null,
): TaskProgressState<T> {
  const [attempt, setAttempt] = useState(0)
  const [snapshot, setSnapshot] = useState<ProgressSnapshot<T>>({
    taskId: null,
    owner: null,
    attempt: 0,
    task: null,
    paused: false,
  })
  const failures = useRef(0)
  const generation = useRef(0)

  useEffect(() => {
    failures.current = 0
    if (!taskId || !owner) return
    const controller = new AbortController()
    const operation = ++generation.current
    let timer: ReturnType<typeof setTimeout> | null = null
    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    }
    const patch = (update: Partial<ProgressSnapshot<T>>): void => {
      if (controller.signal.aborted || operation !== generation.current) return
      setSnapshot((previous) => ({
        ...previous,
        taskId,
        owner,
        attempt,
        ...update,
      }))
    }
    const tick = async (): Promise<void> => {
      if (controller.signal.aborted || operation !== generation.current) return
      try {
        const task = await client.task(taskId, controller.signal)
        if (controller.signal.aborted || operation !== generation.current)
          return
        failures.current = 0
        patch({ task })
        if (TERMINAL.has(task.status) || task.status === 'paused') {
          clearTimer()
          patch({ paused: true })
          return
        }
        timer = setTimeout(() => void tick(), POLL_MS)
      } catch {
        if (controller.signal.aborted || operation !== generation.current)
          return
        failures.current += 1
        if (failures.current >= MAX_CONSECUTIVE_FAILURES) {
          clearTimer()
          patch({ paused: true })
          return
        }
        timer = setTimeout(() => void tick(), POLL_MS)
      }
    }
    void tick()
    return () => {
      controller.abort()
      clearTimer()
    }
  }, [client, taskId, owner, attempt])
  const current =
    snapshot.taskId === taskId &&
    snapshot.owner === owner &&
    snapshot.attempt === attempt
  return {
    task: current ? snapshot.task : null,
    paused: current ? snapshot.paused : false,
    reload: () => {
      failures.current = 0
      setAttempt((value) => value + 1)
    },
  }
}
