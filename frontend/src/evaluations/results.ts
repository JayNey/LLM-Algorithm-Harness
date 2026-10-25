import { ApiClientError } from '../auth/http.ts'
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
  const [task, result] = await Promise.allSettled([
    client.get(id, signal),
    client.result(id, page, signal),
  ])
  signal.throwIfAborted()
  if (task.status === 'rejected') throw task.reason
  if (result.status === 'rejected') {
    if (
      result.reason instanceof ApiClientError &&
      [401, 429].includes(result.reason.status ?? 0)
    )
      throw result.reason
    return {
      ...task.value,
      result: null,
      resultError: '结果暂不可读取，请重试',
    }
  }
  return { ...task.value, result: result.value, resultError: null }
}
