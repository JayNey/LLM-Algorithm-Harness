import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import { fetchEvaluationResult } from './results.ts'
import type { Evaluation, ResultDetail } from './types.ts'

const task: Evaluation = {
  evaluation_id: 'evaluation-without-run',
  created_at: '2026-10-25',
  updated_at: '2026-10-25',
  status: 'running',
  can_start: false,
  can_cancel: true,
  execution_progress: { completed_units: 1, total_units: 2, percentage: 50 },
  strategy_names: ['direct'],
  model: 'm',
  problem_count: 2,
  spent_usd: 0,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
}
const result: ResultDetail = {
  run_id: null,
  status: 'running',
  created_at: '2026-10-25',
  completed_at: null,
  strategies: [],
  problems: { items: [], total: 0, limit: 1, offset: 2, has_more: false },
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('联合快照并发读取相同evaluation ID/分页/signal，结果前不结束周期，run_id可为空', async () => {
  const a = deferred<Evaluation>(),
    b = deferred<ResultDetail>()
  const controller = new AbortController()
  const calls: string[] = []
  const pending = fetchEvaluationResult(
    {
      get: (id, signal) => {
        assert.equal(signal, controller.signal)
        calls.push(id)
        return a.promise
      },
      result: (id, page, signal) => {
        assert.equal(signal, controller.signal)
        assert.deepEqual(page, { limit: 1, offset: 2 })
        calls.push(id)
        return b.promise
      },
    },
    task.evaluation_id,
    { limit: 1, offset: 2 },
    controller.signal,
  )
  assert.deepEqual(calls, [task.evaluation_id, task.evaluation_id])
  let finished = false
  void pending.then(() => {
    finished = true
  })
  a.resolve(task)
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(finished, false)
  b.resolve(result)
  assert.deepEqual(await pending, { ...task, result, resultError: null })
})

test('结果503保留成功任务和独立错误，不伪装合法空结果', async () => {
  const snapshot = await fetchEvaluationResult(
    {
      get: async () => task,
      result: async () => {
        throw new ApiClientError('private upstream error', 503)
      },
    },
    task.evaluation_id,
    { limit: 20, offset: 0 },
    new AbortController().signal,
  )
  assert.equal(snapshot.evaluation_id, task.evaluation_id)
  assert.equal(snapshot.result, null)
  assert.equal(snapshot.resultError, '结果暂不可读取，请重试')
})

test('任务权限失败不发布同时读到的结果', async () => {
  const error = new ApiClientError('not found', 404)
  await assert.rejects(
    fetchEvaluationResult(
      {
        get: async () => {
          throw error
        },
        result: async () => result,
      },
      task.evaluation_id,
      { limit: 20, offset: 0 },
      new AbortController().signal,
    ),
    (e) => e === error,
  )
})

test('结果401/429交还同一观察器恢复/退避，不被普通结果错误吞掉', async () => {
  for (const status of [401, 429]) {
    const error = new ApiClientError('request denied', status)
    await assert.rejects(
      fetchEvaluationResult(
        {
          get: async () => task,
          result: async () => {
            throw error
          },
        },
        task.evaluation_id,
        { limit: 20, offset: 0 },
        new AbortController().signal,
      ),
      (e) => e === error,
    )
  }
})

test('transport忽略AbortSignal时，旧联合结果仍不可交付', async () => {
  const controller = new AbortController(),
    late = deferred<ResultDetail>()
  const pending = fetchEvaluationResult(
    { get: async () => task, result: () => late.promise },
    task.evaluation_id,
    { limit: 20, offset: 0 },
    controller.signal,
  )
  controller.abort()
  late.resolve(result)
  await assert.rejects(pending, { name: 'AbortError' })
})
