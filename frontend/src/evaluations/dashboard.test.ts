import assert from 'node:assert/strict'
import test from 'node:test'
import axios, { type AxiosAdapter } from 'axios'
import { createDashboardClient } from './dashboard.ts'

function row(id: number) {
  return {
    evaluation_id: `task-${id}`,
    created_at: '2026-10-27T01:00:00Z',
    updated_at: '2026-10-27T01:00:00Z',
    status: 'running',
    can_start: false,
    can_cancel: true,
    execution_progress: { completed_units: 2, total_units: 8, percentage: 25 },
    strategy_names: ['direct'],
    model: 'real-model',
    problem_count: 8,
    spent_usd: 0.12,
    budget_cap_usd: null,
    error_message: null,
    progress: null,
  }
}
function client(
  read: (url: string, params: Record<string, unknown>) => unknown,
) {
  const adapter: AxiosAdapter = async (config) => ({
    data: read(config.url!, config.params ?? {}),
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  })
  const http = axios.create({ adapter })
  http.interceptors.response.use((response) => response.data)
  return createDashboardClient(http)
}
function page(items: unknown[], total: number, limit = 5, offset = 0) {
  return { items, total, limit, offset, has_more: offset + limit < total }
}

test('recent reads the tail of ascending pagination and retains full total', async () => {
  const calls: unknown[] = []
  const api = client((url, params) => {
    calls.push([url, params])
    const offset = Number(params.offset)
    return page(
      Array.from({ length: 5 }, (_, i) => row(offset + i)),
      23,
      5,
      offset,
    )
  })
  const result = await api.recent(new AbortController().signal)
  assert.equal(result.total, 23)
  assert.deepEqual(
    result.items.map((item) => item.evaluation_id),
    ['task-22', 'task-21', 'task-20', 'task-19', 'task-18'],
  )
  assert.deepEqual(calls, [
    ['/evaluations', { limit: 5, offset: 0 }],
    ['/evaluations', { limit: 5, offset: 18 }],
  ])
})

test('empty and short histories do not fetch another page', async () => {
  for (const total of [0, 3, 5]) {
    let reads = 0
    const api = client(() => {
      reads++
      return page(
        Array.from({ length: total }, (_, i) => row(i)),
        total,
      )
    })
    assert.equal(
      (await api.recent(new AbortController().signal)).items.length,
      total,
    )
    assert.equal(reads, 1)
  }
})

test('filtered counts use server totals instead of counting the single sample', async () => {
  const api = client((url, params) => {
    assert.equal(url, '/evaluations')
    assert.equal(params.limit, 1)
    assert.equal(params.offset, 0)
    return page([row(1)], params.status === 'running' ? 12 : 91, 1)
  })
  assert.equal(await api.count('running', new AbortController().signal), 12)
  assert.equal(await api.count('completed', new AbortController().signal), 91)
})

test('cost uses owner summary without a date filter and rejects malformed totals', async () => {
  const api = client((url, params) => {
    assert.equal(url, '/costs/summary')
    assert.deepEqual(params, {})
    return { total_cost_usd: 17.123456 }
  })
  assert.equal(await api.cost(new AbortController().signal), 17.123456)
  for (const total of [undefined, null, '17', -1, Infinity]) {
    await assert.rejects(
      client(() => ({ total_cost_usd: total })).cost(
        new AbortController().signal,
      ),
    )
  }
})

test('system is never queried for a user or unconfirmed role', async () => {
  const api = client(() => {
    throw new Error('privileged endpoint called')
  })
  for (const role of [null, 'user'] as const)
    assert.equal(await api.system(role, new AbortController().signal), null)
})

test('failed recent request rejects rather than fabricating empty data', async () => {
  await assert.rejects(
    client(() => {
      throw new Error('offline')
    }).recent(new AbortController().signal),
    /offline/,
  )
})

test('aborted requests cannot initiate a follow-up page', async () => {
  const controller = new AbortController()
  let reads = 0
  const api = client(() => {
    reads++
    controller.abort()
    return page([row(1)], 23)
  })
  await assert.rejects(api.recent(controller.signal))
  assert.equal(reads, 1)
})
