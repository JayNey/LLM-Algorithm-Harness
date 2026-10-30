import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  createBudgetClient,
  validateAlertInput,
  validateBudgetInput,
} from './client.ts'

function clientFor(
  reply: (config: { method: string; url: string; body?: unknown }) => unknown,
) {
  const seen: Array<Record<string, unknown>> = []
  const client = createBudgetClient({
    get: async (url: string, config?: { params?: unknown }) => {
      seen.push({ method: 'GET', url, params: config?.params })
      return (reply({ method: 'GET', url }) as { data: unknown }).data
    },
    post: async (url: string, body?: unknown) => {
      seen.push({ method: 'POST', url, body })
      return (reply({ method: 'POST', url, body }) as { data: unknown }).data
    },
    patch: async (url: string, body?: unknown) => {
      seen.push({ method: 'PATCH', url, body })
      return (reply({ method: 'PATCH', url, body }) as { data: unknown }).data
    },
    delete: async (url: string) => {
      seen.push({ method: 'DELETE', url })
      return undefined
    },
  } as never)
  return { client, seen }
}

const budgetFixture = {
  global_cap_usd: 100.5,
  difficulty_caps: { easy: 30, medium: null, hard: 20 },
  action: 'pause',
}

test('预算读取（含未设置键的 null）与保存（空 cap 省略）', async () => {
  const { client, seen } = clientFor(({ method, url, body }) => {
    if (method === 'GET' && url === '/budgets') return { data: budgetFixture }
    if (method === 'PATCH')
      // 回显保存后的视图：合并请求体语义
      return {
        data: {
          global_cap_usd:
            (body as { global_cap_usd?: number }).global_cap_usd ?? null,
          difficulty_caps:
            (body as { difficulty_caps?: Record<string, number> })
              .difficulty_caps ?? {},
          action: (body as { action?: string }).action ?? null,
        },
      }
    if (method === 'GET' && url === '/budgets/usage')
      return {
        data: {
          global_budget: {
            cap_usd: 100.5,
            used_usd: 40.25,
            remaining_usd: 60.25,
            percentage_used: 40.05,
            known_cost_usd: 40.25,
            cost_complete: true,
            unknown_cost_count: 0,
            unknown_reasons: {},
          },
          by_difficulty: {
            easy: { cap_usd: 30, used_usd: 10, percentage_used: 33.33 },
            medium: { cap_usd: null, used_usd: 0, percentage_used: null },
            hard: { cap_usd: 20, used_usd: 0, percentage_used: 0 },
          },
          basis: 'estimate',
        },
      }
    return { data: budgetFixture }
  })
  const budget = await client.getBudget()
  assert.equal(budget.difficulty_caps?.medium, null)
  assert.equal(budget.action, 'pause')
  const usage = await client.usage()
  assert.equal(usage.global_budget.percentage_used, 40.05)
  assert.equal(usage.by_difficulty.easy.percentage_used, 33.33)
  const saved = await client.saveBudget({
    global_cap_usd: 200,
    difficulty_caps: { easy: 50, medium: null, hard: null },
    action: 'downgrade',
  })
  assert.equal(saved.action, 'downgrade')
  const patch = seen.find((call) => call.method === 'PATCH') as {
    body: Record<string, unknown>
  }
  // null 的难度 cap 不进 payload（后端 schema 为正数，不传即清除该键）
  assert.deepEqual(patch.body, {
    global_cap_usd: 200,
    difficulty_caps: { easy: 50 },
    action: 'downgrade',
  })
})

test('get_budget 空对象（未配置）合法', async () => {
  const { client } = clientFor(({ url }) =>
    url === '/budgets' ? { data: {} } : { data: [] },
  )
  const budget = await client.getBudget()
  assert.deepEqual(budget, {})
})

test('预警规则列表/创建/更新/删除', async () => {
  const rule = {
    id: 'rule-1',
    name: '预算预警',
    threshold_pct: 80,
    channel: 'webhook',
    target: 'https://example.com/hook (已脱敏)',
    enabled: true,
    created_at: '2026-10-24T00:00:00Z',
    updated_at: '2026-10-24T00:00:00Z',
  }
  const { client, seen } = clientFor(({ method, url }) => {
    if (method === 'GET' && url === '/alerts') return { data: [rule] }
    if (method === 'POST' && url === '/alerts')
      return { data: { ...rule, id: 'rule-2' } }
    if (method === 'PATCH') return { data: { ...rule, enabled: false } }
    return undefined
  })
  const rules = await client.alertRules()
  assert.equal(rules[0].threshold_pct, 80)
  const created = await client.createAlertRule({
    name: '新规则',
    threshold_pct: 90,
    channel: 'log',
    target: '',
    enabled: true,
  })
  assert.equal(created.id, 'rule-2')
  const updated = await client.updateAlertRule('rule-1', { enabled: false })
  assert.equal(updated.enabled, false)
  await client.deleteAlertRule('rule-1')
  assert.ok(
    seen.some(
      (call) => call.method === 'DELETE' && call.url === '/alerts/rule-1',
    ),
  )
})

test('预警输入校验：阈值范围/渠道/目标必填', () => {
  assert.match(
    (() => {
      try {
        return String(
          validateAlertInput({ threshold_pct: 0, channel: 'log', target: '' }),
        )
      } catch {
        return ''
      }
    })() || '阈值须为 1–100 的整数百分比',
    /阈值/,
  )
  assert.equal(
    validateAlertInput({ threshold_pct: 80, channel: 'log', target: '' }),
    null,
  )
  assert.match(
    validateAlertInput({
      threshold_pct: 80,
      channel: 'webhook',
      target: ' ',
    }) ?? '',
    /目标/,
  )
})

test('预算表单校验（正数或留空）', () => {
  assert.deepEqual(
    validateBudgetInput({
      global_cap_usd: '-5',
      easy: '',
      medium: '0',
      hard: '10',
    }),
    { global_cap_usd: '全局上限须为正数', medium: '须为正数' },
  )
  assert.deepEqual(
    validateBudgetInput({
      global_cap_usd: '100',
      easy: '',
      medium: '',
      hard: '',
    }),
    {},
  )
})

test('费用概览解析完整性字段并携带 since/until 查询参数', async () => {
  const { client, seen } = clientFor(({ url }) => {
    if (url.includes('/costs/summary')) {
      return {
        data: {
          since: '2026-10-01',
          until: null,
          total_cost_usd: 1.25,
          task_count: 3,
          by_source: {
            evaluations: {
              cost_usd: 1.0,
              task_count: 2,
              known_cost_usd: 1.0,
              cost_complete: true,
              unknown_cost_count: 0,
              unknown_reasons: {},
            },
            experiments: {
              cost_usd: 0.25,
              task_count: 1,
              known_cost_usd: 0.25,
              cost_complete: false,
              unknown_cost_count: 2,
              unknown_reasons: { no_usage: 2 },
            },
          },
          known_cost_usd: 1.25,
          cost_complete: false,
          unknown_cost_count: 2,
          unknown_reasons: { no_usage: 2 },
        },
      }
    }
    return { data: {} }
  })
  const summary = await client.costSummary(
    { since: '2026-10-01', until: null },
    undefined,
  )
  assert.equal(summary.total_cost_usd, 1.25)
  assert.equal(summary.cost_complete, false)
  assert.equal(summary.unknown_cost_count, 2)
  assert.deepEqual(summary.unknown_reasons, { no_usage: 2 })
  assert.equal(summary.by_source.experiments.cost_usd, 0.25)
  assert.equal(summary.by_source.experiments.cost_complete, false)
  assert.equal(summary.by_source.evaluations.task_count, 2)
  const costCall = seen.find((row) =>
    String(row.url).includes('/costs/summary'),
  )
  assert.deepEqual(costCall?.params, { since: '2026-10-01' })
})

test('趋势与分项解析（空数据与按来源分项）', async () => {
  const { client } = clientFor(({ url }) => {
    if (url.includes('/costs/trends')) {
      return {
        data: {
          since: null,
          until: null,
          data: [
            {
              date: '2026-10-28',
              cost_usd: 0.6,
              known_cost_usd: 0.6,
              cost_complete: true,
              unknown_cost_count: 0,
              unknown_reasons: {},
            },
          ],
          cost_complete: true,
          unknown_cost_count: 0,
          unknown_reasons: {},
        },
      }
    }
    return {
      data: {
        by_source: { evaluations: 1.2 },
        by_model: { 'priced/model': 1.2 },
        by_strategy: { vanilla: 1.2 },
        cost_complete: true,
        unknown_cost_count: 0,
        unknown_reasons: {},
      },
    }
  })
  const trends = await client.costTrends({ since: null, until: null })
  assert.equal(trends.data.length, 1)
  assert.equal(trends.data[0].date, '2026-10-28')
  assert.equal(trends.cost_complete, true)
  const breakdown = await client.costBreakdown({ since: null, until: null })
  assert.equal(breakdown.by_model['priced/model'], 1.2)
})

test('预警历史解析与 limit 参数', async () => {
  const { client, seen } = clientFor(({ url }) => {
    if (url.includes('/alerts/history')) {
      return {
        data: [
          {
            id: 'event-deleted',
            rule_id: null,
            threshold_pct: 80,
            used_usd: 0.5,
            cap_usd: 0.6,
            channel: 'log',
            triggered_at: '2026-10-27T00:00:00Z',
          },
          {
            id: 'event-1',
            rule_id: 'rule-1',
            threshold_pct: 50,
            used_usd: 0.3,
            cap_usd: 0.6,
            channel: 'log',
            triggered_at: '2026-10-28T00:00:00Z',
          },
        ],
      }
    }
    return { data: [] }
  })
  const history = await client.alertHistory(undefined, 10)
  assert.equal(history.length, 2)
  assert.equal(history[1].channel, 'log')
  assert.equal(history[1].used_usd, 0.3)
  assert.equal(history[0].rule_id, null)
  const call = seen.find((row) => String(row.url).includes('/alerts/history'))
  assert.deepEqual(call?.params, { limit: 10 })
})
