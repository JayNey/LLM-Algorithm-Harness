import { ApiClientError } from '../auth/http.ts'
import { isSettledStatus } from './observer.ts'
import type {
  EvaluationClient,
  EvaluationSnapshot,
  PageQuery,
} from './types.ts'

/** One observer cycle owns both reads; partial result failure is not an empty result. */
export async function fetchEvaluationResult(
  client: Pick<EvaluationClient, 'get' | 'result'>,
  id: string,
  page: PageQuery,
  signal: AbortSignal,
): Promise<EvaluationSnapshot> {
  const [task, firstResult] = await Promise.allSettled([
    client.get(id, signal),
    client.result(id, page, signal),
  ])
  signal.throwIfAborted()
  if (task.status === 'rejected') throw task.reason
  let result = firstResult
  // The concurrent reads can straddle the worker's terminal commit. Complete
  // one ordered reconciliation inside this cycle before the observer settles.
  if (
    isSettledStatus(task.value.status) &&
    result.status === 'fulfilled' &&
    result.value.status !== task.value.status
  ) {
    ;[result] = await Promise.allSettled([client.result(id, page, signal)])
    signal.throwIfAborted()
  }
  if (result.status === 'rejected') {
    if (
      result.reason instanceof ApiClientError &&
      [401, 403, 404, 429].includes(result.reason.status ?? 0)
    )
      throw result.reason
    return {
      ...task.value,
      result: null,
      resultError: '结果暂不可读取，请重试',
    }
  }
  if (
    isSettledStatus(task.value.status) &&
    result.value.status !== task.value.status
  )
    return {
      ...task.value,
      result: null,
      resultError: '结果快照与任务状态暂不一致，请重试',
    }
  return { ...task.value, result: result.value, resultError: null }
}
