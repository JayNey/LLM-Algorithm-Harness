import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { InternalAxiosRequestConfig } from 'axios'
import { ApiClientError, createHttpClient } from '../auth/http.ts'
import { analyticsQuery, createAnalyticsClient } from './analytics.ts'

const bucket = { success_rate: 0.5, solved: 1, total: 2 }
const strategy = {
  name: 'direct',
  success_rate: 0.5,
  total_problems: 2,
  solved_problems: 1,
  avg_tokens: 12,
  estimated_cost_usd: 0,
  unknown_cost_count: 2,
  avg_execution_time: 1.5,
  by_difficulty: { easy: bucket },
}
const successRate = {
  ...bucket,
  avg_execution_time: 1.5,
  by_difficulty: { easy: bucket },
  by_tag: { graph: bucket },
}
const tokens = {
  total_tokens: 100,
  avg_tokens: 25,
  estimated_cost_usd: 0.2,
  unknown_cost_count: 1,
}
const iterations = {
  known_count: 3,
  unknown_count: 1,
  average: 2,
  distribution: [{ iterations: 1, count: 1 }],
}
const failureModes = { logic_error: 1, unknown: 2 }
const successRateChart = { points: [{ name: 'direct', success_rate: 1 }] }
const tokenChart = {
  series: [
    {
      name: 'direct',
      points: [
        { problem_id: 'p1', tokens: 10 },
        { problem_id: 'p2', tokens: null },
      ],
    },
  ],
}
const costAccuracy = {
  points: [{ name: 'direct', success_rate: 1, estimated_cost_usd: 0.2 }],
}
const dimensions = [
  'Array',
  'Graph',
  'Dynamic Programming',
  'Greedy',
  'Math',
  'String',
  'Other',
]
const radar = {
  dimensions,
  series: [
    { name: 'model-a', data: [50, 0, 0, 0, 0, 0, 0] },
    { name: null, data: [0, 0, 0, 0, 0, 0, 100] },
  ],
  problem_counts: Object.fromEntries(dimensions.map((name) => [name, 0])),
}
const byTag = { tags: { graph: bucket } }
const summary = {
  modes: { logic_error: 1 },
  categories: { wrong_answer: 1 },
  clusters: [{ pattern: 'boom N', count: 1 }],
}
const cases = {
  items: [
    {
      problem_id: 'p1',
      strategy: 'direct',
      status: 'failed',
      error_message: 'x',
    },
    {
      problem_id: 'p2',
      strategy: 'direct',
      status: 'failed',
      error_message: null,
    },
    {
      problem_id: 'p3',
      strategy: 'direct',
      status: 'pending',
      error_message: '',
    },
  ],
}
const strategies = { strategies: [strategy] }
const models = {
  models: [
    { model: 'model-a', strategies: [strategy] },
    { model: null, strategies: [] },
  ],
}
const history = {
  series: [
    { run_id: 'run-1', completed_at: '2026-10-01T00:00:00Z', strategies: [] },
    { run_id: null, completed_at: null, strategies: [strategy] },
  ],
}
const replies: Record<string, unknown> = {
  '/analytics/success-rate': successRate,
  '/analytics/tokens': tokens,
  '/analytics/iterations': iterations,
  '/analytics/failure-modes': failureModes,
  '/visualizations/success-rate-chart': successRateChart,
  '/visualizations/token-chart': tokenChart,
  '/visualizations/cost-accuracy': costAccuracy,
  '/visualizations/capability-radar': radar,
  '/failures/by-tag': byTag,
  '/failures/summary/run%2F1': summary,
  '/failures/cases/run%2F1': cases,
  '/compare/strategies': strategies,
  '/compare/models': models,
  '/compare/history': history,
}

function clientFor(
  reply: unknown | ((config: InternalAxiosRequestConfig) => unknown),
  seen: InternalAxiosRequestConfig[] = [],
) {
  return createAnalyticsClient(
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
const run = { kind: 'run', runId: 'run/1' } as const
const account = { kind: 'account' } as const

test('十四个接口走已解包认证客户端：URL、20 s 超时、编码 ID、signal 与 Cookie', async () => {
  const seen: InternalAxiosRequestConfig[] = []
  const client = clientFor(
    (config: InternalAxiosRequestConfig) => replies[config.url ?? ''],
    seen,
  )
  const signal = new AbortController().signal
  const filters = { strategy: 'direct', difficulty: 'easy', tag: 'graph' }
  assert.deepEqual(await client.successRate(run, filters, signal), successRate)
  assert.deepEqual(await client.tokens(run, filters, signal), tokens)
  assert.deepEqual(await client.iterations(run, filters, signal), iterations)
  assert.deepEqual(
    await client.failureModes(run, filters, signal),
    failureModes,
  )
  assert.deepEqual(
    await client.successRateChart(run, filters, signal),
    successRateChart,
  )
  assert.deepEqual(await client.tokenChart(run, filters, signal), tokenChart)
  assert.deepEqual(
    await client.costAccuracy(run, filters, signal),
    costAccuracy,
  )
  assert.deepEqual(await client.capabilityRadar(run, filters, signal), radar)
  assert.deepEqual(await client.failuresByTag(run, filters, signal), byTag)
  assert.deepEqual(await client.failureSummary('run/1', signal), summary)
  assert.deepEqual(await client.failureCases('run/1', signal), cases)
  assert.deepEqual(await client.compareStrategies('run/1', signal), strategies)
  assert.deepEqual(await client.compareModels(signal), models)
  assert.deepEqual(await client.compareHistory('run/1', signal), history)
  assert.deepEqual(
    seen.map((config) => [config.method, config.url, config.timeout]),
    Object.keys(replies).map((url) => ['get', url, 20000]),
  )
  const scoped = { run_id: 'run/1', ...filters }
  assert.deepEqual(
    seen.slice(0, 9).map((config) => config.params),
    Array.from({ length: 9 }, () => scoped),
  )
  assert.equal(seen[9]?.params, undefined)
  assert.equal(seen[10]?.params, undefined)
  assert.deepEqual(seen[11]?.params, { run_id: 'run/1' })
  assert.equal(seen[12]?.params, undefined)
  assert.deepEqual(seen[13]?.params, { run_id: 'run/1' })
  for (const config of seen) {
    assert.equal(config.signal, signal)
    assert.equal(config.withCredentials, true)
  }
})

test('查询白名单：全账号不带 run_id，空白筛选与未知键被丢弃，空 ID 不发请求', async () => {
  assert.deepEqual(analyticsQuery(account, {}), {})
  assert.deepEqual(
    analyticsQuery(account, { strategy: ' ', difficulty: '', tag: 'Graph' }),
    { tag: 'Graph' },
  )
  assert.deepEqual(
    analyticsQuery(run, {
      strategy: 'direct',
      ...({ limit: 20, run_id: 'other' } as object),
    }),
    { run_id: 'run/1', strategy: 'direct' },
  )
  const seen: InternalAxiosRequestConfig[] = []
  const client = clientFor(successRate, seen)
  await assert.rejects(
    () => client.successRate({ kind: 'run', runId: ' ' }, {}),
    (error: unknown) =>
      error instanceof ApiClientError && error.message === '缺少资源 ID',
  )
  await assert.rejects(() => client.failureCases(''), ApiClientError)
  await assert.rejects(() => client.compareHistory(''), ApiClientError)
  assert.equal(seen.length, 0)
  await client.successRate(account, { tag: 'Graph' })
  assert.deepEqual(seen[0]?.params, { tag: 'Graph' })
})

test('合法空数据与可空字段保持真实值，不填零', async () => {
  assert.deepEqual(
    await clientFor({
      ...bucket,
      success_rate: 0,
      solved: 0,
      total: 0,
      avg_execution_time: 0,
      by_difficulty: {},
      by_tag: {},
    }).successRate(account, {}),
    {
      success_rate: 0,
      solved: 0,
      total: 0,
      avg_execution_time: 0,
      by_difficulty: {},
      by_tag: {},
    },
  )
  assert.equal(
    (await clientFor({ ...iterations, average: null }).iterations(account, {}))
      .average,
    null,
  )
  assert.deepEqual(await clientFor({}).failureModes(account, {}), {})
  assert.equal(
    (await clientFor(tokenChart).tokenChart(run, {})).series[0]?.points[1]
      ?.tokens,
    null,
  )
  assert.equal(
    (await clientFor(radar).capabilityRadar(run, {})).series[1]?.name,
    null,
  )
  assert.deepEqual(await clientFor({ points: [] }).costAccuracy(run, {}), {
    points: [],
  })
  assert.deepEqual(await clientFor({ series: [] }).compareHistory('r'), {
    series: [],
  })
  assert.equal(
    (await clientFor(cases).failureCases('r')).items[2]?.error_message,
    '',
  )
})

test('缺字段、非法类型与越界值明确拒绝，并带字段路径', async () => {
  const rejects = async (
    call: () => Promise<unknown>,
    field?: string,
  ): Promise<void> => {
    await assert.rejects(call, (error: unknown) => {
      assert.ok(error instanceof ApiClientError)
      assert.equal(error.message, '结果分析接口响应格式不兼容')
      if (field) assert.equal(error.details?.field, field)
      return true
    })
  }
  for (const field of Object.keys(successRate)) {
    const invalid: Record<string, unknown> = { ...successRate }
    delete invalid[field]
    await rejects(() => clientFor(invalid).successRate(run, {}))
  }
  await rejects(
    () => clientFor({ ...successRate, success_rate: 1.2 }).successRate(run, {}),
    'success_rate.success_rate',
  )
  await rejects(
    () => clientFor({ ...successRate, solved: 1.5 }).successRate(run, {}),
    'success_rate.solved',
  )
  await rejects(
    () =>
      clientFor({
        ...successRate,
        by_tag: { graph: { solved: 1 } },
      }).successRate(run, {}),
    'success_rate.by_tag.graph.success_rate',
  )
  await rejects(
    () => clientFor({ ...tokens, unknown_cost_count: -1 }).tokens(run, {}),
    'tokens.unknown_cost_count',
  )
  await rejects(
    () => clientFor({ ...tokens, estimated_cost_usd: '0.2' }).tokens(run, {}),
    'tokens.estimated_cost_usd',
  )
  await rejects(
    () =>
      clientFor({
        ...iterations,
        distribution: [{ iterations: 1 }],
      }).iterations(run, {}),
    'iterations.distribution.0.count',
  )
  await rejects(
    () => clientFor({ logic_error: '1' }).failureModes(run, {}),
    'failure_modes.logic_error',
  )
  await rejects(() => clientFor([]).failureModes(run, {}), 'failure_modes')
  await rejects(
    () =>
      clientFor({ points: [{ name: '', success_rate: 1 }] }).successRateChart(
        run,
        {},
      ),
    'success_rate_chart.points.0.name',
  )
  await rejects(
    () =>
      clientFor({
        series: [{ name: 'd', points: [{ problem_id: 'p', tokens: -1 }] }],
      }).tokenChart(run, {}),
    'token_chart.series.0.points.0.tokens',
  )
  await rejects(
    () =>
      clientFor({ points: [{ name: 'd', success_rate: 1 }] }).costAccuracy(
        run,
        {},
      ),
    'cost_accuracy.points.0.estimated_cost_usd',
  )
  await rejects(
    () =>
      clientFor({
        ...radar,
        series: [{ name: 'm', data: [50, 0] }],
      }).capabilityRadar(run, {}),
    'capability_radar.series.0.data',
  )
  await rejects(
    () =>
      clientFor({
        ...radar,
        series: [{ name: 'm', data: [101, 0, 0, 0, 0, 0, 0] }],
      }).capabilityRadar(run, {}),
    'capability_radar.series.0.data.0',
  )
  await rejects(
    () =>
      clientFor({ ...radar, problem_counts: { Array: 0.5 } }).capabilityRadar(
        run,
        {},
      ),
    'capability_radar.problem_counts.Array',
  )
  await rejects(
    () => clientFor({ tags: [] }).failuresByTag(run, {}),
    'failures_by_tag.tags',
  )
  await rejects(
    () =>
      clientFor({ ...summary, clusters: [{ pattern: 'x' }] }).failureSummary(
        'r',
      ),
    'failure_summary.clusters.0.count',
  )
  await rejects(
    () =>
      clientFor({
        items: [
          { problem_id: 'p', strategy: 'd', status: '', error_message: null },
        ],
      }).failureCases('r'),
    'failure_cases.items.0.status',
  )
  await rejects(
    () =>
      clientFor({
        strategies: [{ ...strategy, unknown_cost_count: 1.5 }],
      }).compareStrategies('r'),
    'compare_strategies.strategies.0.unknown_cost_count',
  )
  await rejects(
    () => clientFor({ models: [{ strategies: [] }] }).compareModels(),
    'compare_models.models.0.model',
  )
  await rejects(
    () =>
      clientFor({ series: [{ run_id: 'r', strategies: [] }] }).compareHistory(
        'r',
      ),
    'compare_history.series.0.completed_at',
  )
  await rejects(() => clientFor(null).compareModels(), 'compare_models')
})
