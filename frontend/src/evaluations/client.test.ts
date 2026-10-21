import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { InternalAxiosRequestConfig } from 'axios'
import { ApiClientError, createHttpClient } from '../auth/http.ts'
import { createEvaluationClient } from './client.ts'
import type { Evaluation, CreatePayload } from './types.ts'

const evaluation: Evaluation = {
  evaluation_id: 'eval1',
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
  status: 'pending',
  can_start: true,
  can_cancel: false,
  execution_progress: { completed_units: 0, total_units: 2, percentage: 0 },
  strategy_names: ['direct'],
  model: 'model-a',
  problem_count: 2,
  spent_usd: 0,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
}
const payload: CreatePayload = {
  api_key_id: 'k1',
  model: 'model-a',
  problem_ids: ['p1', 'p2'],
  strategy_names: ['direct'],
}
const page = <T>(items: T[], total = items.length) => ({
  items,
  total,
  limit: 20,
  offset: 0,
  has_more: false,
})
const summary = {
  id: 'eval1',
  run_id: null,
  status: 'pending',
  model: null,
  strategy_names: ['direct'],
  created_at: '2026-10-21T00:00:00Z',
  completed_at: null,
}
const strategy = {
  name: 'direct',
  success_rate: 0.5,
  total_problems: 2,
  solved_problems: 1,
  avg_tokens: 0,
  estimated_cost_usd: 0,
  unknown_cost_count: 2,
  avg_execution_time: 0,
  by_difficulty: { easy: { success_rate: 0.5, solved: 1, total: 2 } },
}
const detail = {
  run_id: null,
  status: 'pending',
  created_at: '2026-10-21T00:00:00Z',
  completed_at: null,
  strategies: [strategy],
  problems: page([
    {
      problem_id: 'p1',
      strategy: 'direct',
      status: 'success',
      iterations: null,
      tokens: null,
      execution_time: null,
    },
  ]),
}

function clientFor(
  reply: unknown | ((config: InternalAxiosRequestConfig) => unknown),
  seen: InternalAxiosRequestConfig[] = [],
) {
  return createEvaluationClient(
    createHttpClient({
      baseURL: 'http://api.test/api/v1',
      now: () => 0,
      read: () => ({
        marker: 'user1',
        expiresAt: 100_000,
        username: 'ada',
        csrfToken: 'csrf1',
      }),
      write: () => undefined,
      clear: () => undefined,
      adapter: async (config) => {
        seen.push(config)
        const response = typeof reply === 'function' ? reply(config) : reply
        return {
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
          data: { success: true, data: response, message: '' },
        }
      },
    }),
  )
}

test('十个方法使用已解包认证客户端，编码ID、白名单查询、signal和真实payload', async () => {
  const seen: InternalAxiosRequestConfig[] = []
  const client = clientFor((config: InternalAxiosRequestConfig) => {
    if (config.url === '/evaluation-options')
      return {
        strategies: [{ name: 'direct' }],
        sources: [{ id: 'shared', label: '共享', problem_count: 2 }],
      }
    if (config.url === '/evaluation-options/problems')
      return page([
        { problem_id: 'p1', title: '题目', difficulty: null, source: 'shared' },
      ])
    if (config.url === '/evaluation-options/models')
      return { provider: 'openai', models: ['model-a'], complete: false }
    if (config.url === '/evaluations' && config.method === 'get')
      return page([evaluation])
    if (config.url === '/results') return page([summary])
    if (config.url?.startsWith('/results/')) return detail
    return evaluation
  }, seen)
  const signal = new AbortController().signal
  assert.equal((await client.options(signal)).sources[0]?.problem_count, 2)
  assert.equal(
    (
      await client.problems(
        { source: 'personal', limit: 20, offset: 40 },
        signal,
      )
    ).items[0]?.difficulty,
    null,
  )
  assert.equal((await client.models('key/id', signal)).complete, false)
  assert.equal(
    (
      await client.list(
        { status: 'paused', limit: 20, offset: 0, name: 'ignored' } as never,
        signal,
      )
    ).items[0]?.evaluation_id,
    'eval1',
  )
  assert.equal((await client.get('other/id', signal)).evaluation_id, 'eval1')
  assert.equal(
    (
      await client.create({
        ...payload,
        name: 'ignored',
        dataset: 'ignored',
      } as never)
    ).can_start,
    true,
  )
  assert.equal((await client.start('other/id')).status, 'pending')
  assert.equal((await client.cancel('other/id')).can_cancel, false)
  assert.equal(
    (
      await client.results(
        { status: 'completed', limit: 20, offset: 0 },
        signal,
      )
    ).items[0]?.id,
    'eval1',
  )
  const parsed = await client.result(
    'other/id',
    { limit: 10, offset: 20, status: 'ignored' } as never,
    signal,
  )
  assert.equal(parsed.run_id, null)
  assert.deepEqual(parsed.problems.items[0], {
    problem_id: 'p1',
    strategy: 'direct',
    status: 'success',
    iterations: null,
    tokens: null,
    execution_time: null,
  })
  assert.deepEqual(
    seen.map((config) => [config.method, config.url, config.timeout]),
    [
      ['get', '/evaluation-options', 10000],
      ['get', '/evaluation-options/problems', 10000],
      ['get', '/evaluation-options/models', 20000],
      ['get', '/evaluations', 10000],
      ['get', '/evaluations/other%2Fid', 10000],
      ['post', '/evaluations', 20000],
      ['post', '/evaluations/other%2Fid/start', 20000],
      ['post', '/evaluations/other%2Fid/cancel', 20000],
      ['get', '/results', 10000],
      ['get', '/results/other%2Fid', 10000],
    ],
  )
  assert.deepEqual(seen[1]?.params, {
    source: 'personal',
    limit: 20,
    offset: 40,
  })
  assert.deepEqual(seen[2]?.params, { api_key_id: 'key/id' })
  assert.deepEqual(seen[3]?.params, { status: 'paused', limit: 20, offset: 0 })
  assert.deepEqual(seen[9]?.params, { limit: 10, offset: 20 })
  assert.deepEqual(JSON.parse(seen[5]?.data as string), payload)
  for (const config of seen.filter((value) => value.method === 'get'))
    assert.equal(config.signal, signal)
  for (const config of seen) assert.equal(config.withCredentials, true)
  assert.equal(seen[5]?.headers.get('X-CSRF-Token'), 'csrf1')
})

test('合法空页、空模型和未知任务状态保持真实值', async () => {
  assert.deepEqual(
    await clientFor(page([])).list({ limit: 20, offset: 0 }),
    page([]),
  )
  assert.deepEqual(
    await clientFor(page([])).results({ limit: 20, offset: 0 }),
    page([]),
  )
  assert.deepEqual(
    await clientFor({ provider: 'openai', models: [], complete: true }).models(
      'k1',
    ),
    { provider: 'openai', models: [], complete: true },
  )
  assert.equal(
    (await clientFor({ ...evaluation, status: 'future' }).get('e1')).status,
    'future',
  )
})

test('缺少新能力字段或错误字段类型明确拒绝，不造默认值', async () => {
  for (const field of Object.keys(evaluation)) {
    const invalid: Record<string, unknown> = { ...evaluation }
    delete invalid[field]
    await assert.rejects(
      () => clientFor(invalid).get('e1'),
      ApiClientError,
      field,
    )
  }
  for (const patch of [
    { can_start: 1 },
    { can_cancel: null },
    { execution_progress: { completed_units: 0, total_units: 2 } },
    { spent_usd: Infinity },
    { problem_count: NaN },
    { status: '' },
    { model: 42 },
    {
      execution_progress: {
        completed_units: 1,
        total_units: 2,
        percentage: Infinity,
      },
    },
    { progress: { current: 0, total: 2, message: null, percentage: NaN } },
  ])
    await assert.rejects(
      () => clientFor({ ...evaluation, ...patch }).get('e1'),
      ApiClientError,
    )
})

test('分页、选项和结果嵌套契约均严格读取，null指标不填零', async () => {
  for (const invalid of [
    null,
    {},
    { ...page([]), total: Infinity },
    { ...page([]), has_more: undefined },
    { ...page([]), items: [{}] },
  ]) {
    await assert.rejects(
      () => clientFor(invalid).list({ limit: 20, offset: 0 }),
      ApiClientError,
    )
  }
  for (const invalid of [
    {
      strategies: [],
      sources: [{ id: 'other', label: 'x', problem_count: 0 }],
    },
    { strategies: [{}], sources: [] },
  ]) {
    await assert.rejects(() => clientFor(invalid).options(), ApiClientError)
  }
  await assert.rejects(
    () => clientFor({ provider: 'openai', models: ['x'] }).models('k1'),
    ApiClientError,
  )
  await assert.rejects(
    () =>
      clientFor(
        page([{ problem_id: 'p1', title: 'x', source: 'shared' }]),
      ).problems({ source: 'all', limit: 20, offset: 0 }),
    ApiClientError,
  )
  await assert.rejects(
    () =>
      clientFor(page([{ ...summary, id: undefined }])).results({
        limit: 20,
        offset: 0,
      }),
    ApiClientError,
  )
  for (const invalid of [
    { ...detail, run_id: undefined },
    { ...detail, strategies: [{ ...strategy, unknown_cost_count: undefined }] },
    {
      ...detail,
      strategies: [
        {
          ...strategy,
          by_difficulty: { easy: { success_rate: 0.5, solved: 1 } },
        },
      ],
    },
    {
      ...detail,
      problems: page([{ ...detail.problems.items[0], tokens: undefined }]),
    },
    {
      ...detail,
      problems: page([
        { ...detail.problems.items[0], execution_time: Infinity },
      ]),
    },
  ])
    await assert.rejects(
      () => clientFor(invalid).result('e1', { limit: 20, offset: 0 }),
      ApiClientError,
    )
})

test('网络和权限失败原样向上抛出且不重试业务mutation', async () => {
  let calls = 0
  const error = new ApiClientError('不可访问', 403)
  const client = clientFor(() => {
    calls += 1
    throw error
  })
  await assert.rejects(
    () => client.get('other/id'),
    (actual) => actual === error,
  )
  await assert.rejects(
    () => client.start('e1'),
    (actual) => actual === error,
  )
  assert.equal(calls, 2)
})

test('空ID和无效创建输入在网络前拒绝', async () => {
  const seen: InternalAxiosRequestConfig[] = []
  const client = clientFor(evaluation, seen)
  await assert.rejects(() => client.get(' '), ApiClientError)
  await assert.rejects(() => client.models(''), ApiClientError)
  await assert.rejects(
    () => client.create({ ...payload, budget_cap_usd: Infinity }),
    ApiClientError,
  )
  assert.equal(seen.length, 0)
})
