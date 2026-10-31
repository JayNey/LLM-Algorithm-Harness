import { ApiClientError } from '../auth/http.ts'
import type { BenchmarkRun, RunPage, RunStatus, TaskSnapshot } from './types.ts'

export const runStatuses: RunStatus[] = [
  'pending',
  'running',
  'paused',
  'completed',
  'failed',
  'cancelled',
]
export const terminalRun = (status: string) =>
  ['completed', 'failed', 'cancelled'].includes(status)

export function readHistoryQuery(search: URLSearchParams) {
  const ids = search.getAll('run_id')
  const raw = ids[0]
  const invalidRun =
    ids.length > 1 ||
    (raw !== undefined &&
      (!raw.trim() ||
        raw.length > 200 ||
        [...raw].some((c) => c.charCodeAt(0) < 32)))
  const status = search.get('status')
  const offset = search.get('offset') ?? '0'
  return {
    runId: invalidRun ? null : (raw ?? null),
    invalidRun,
    status: runStatuses.includes(status as RunStatus)
      ? (status as RunStatus)
      : undefined,
    offset:
      /^\d+$/.test(offset) && Number.isSafeInteger(Number(offset))
        ? Number(offset)
        : 0,
    limit: 20,
  }
}
export function historySearch(
  search: URLSearchParams,
  patch: { runId?: string; status?: string; offset?: number },
) {
  const next = new URLSearchParams(search)
  if (patch.runId !== undefined) next.set('run_id', patch.runId)
  if (patch.status !== undefined) {
    if (patch.status) next.set('status', patch.status)
    else next.delete('status')
  }
  if (patch.offset !== undefined) {
    if (patch.offset) next.set('offset', String(patch.offset))
    else next.delete('offset')
  }
  return next
}
export function uniqueActiveRun(pages: RunPage[]): string | null {
  return pages.length === 3 && pages.reduce((n, p) => n + p.total, 0) === 1
    ? (pages.flatMap((p) => p.items)[0]?.id ?? null)
    : null
}
export function assertRunAssociation(
  run: BenchmarkRun,
  suiteId: string,
  runId: string,
) {
  if (run.id !== runId || run.suite_id !== suiteId)
    throw new ApiClientError('运行关联不匹配，请重新选择')
  return run
}
export function assertTaskAssociation(
  task: TaskSnapshot,
  taskId: string,
  runId: string,
) {
  if (
    task.id !== taskId ||
    task.entity_id !== runId ||
    task.task_type !== 'benchmark'
  )
    throw new ApiClientError('任务关联不匹配，已停止进度查询', undefined, {
      stopPolling: true,
    })
  return task
}
