import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  evaluationLabel,
  metricLabel,
  resultAvailability,
  successRateLabel,
  resultCostLabel,
  resultStatusLabel,
} from './presentation.ts'
import type { Evaluation, ResultDetail } from './types.ts'

const evaluation: Evaluation = {
  evaluation_id: 'eval1',
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
  can_cancel: false,
  strategy_names: ['direct', 'cot'],
  model: 'model-a',
  problem_count: 2,
  spent_usd: 0,
  budget_cap_usd: null,
  error_message: null,
  progress: null,
  status: 'pending',
  can_start: true,
  execution_progress: { completed_units: 1, total_units: 4, percentage: 25 },
}
const result: ResultDetail = {
  run_id: null,
  created_at: '2026-10-21T00:00:00Z',
  completed_at: null,
  strategies: [],
  status: 'completed',
  problems: { items: [], total: 4, limit: 1, offset: 4, has_more: false },
}

test('未启动和已入队的pending独立展示，未知状态保持中性原值', () => {
  assert.equal(evaluationLabel(evaluation), '待启动')
  assert.equal(
    evaluationLabel({ ...evaluation, can_start: false }),
    '已入队，等待执行',
  )
  for (const [status, label] of [
    ['running', '运行中'],
    ['paused', '已暂停'],
    ['completed', '已完成'],
    ['failed', '失败'],
    ['cancelled', '已取消'],
  ]) {
    assert.equal(evaluationLabel({ ...evaluation, status }), label)
  }
  for (const status of ['future', 'toString', '__proto__']) {
    assert.equal(
      evaluationLabel({ ...evaluation, status }),
      `未知状态（${status}）`,
    )
  }
})

test('结果完整性使用全量记录数和规范化预期数，不依赖当前页或旧progress', () => {
  assert.deepEqual(
    resultAvailability({ ...evaluation, status: 'completed' }, result),
    { kind: 'complete', recorded_units: 4, expected_units: 4 },
  )
  assert.deepEqual(
    resultAvailability(
      { ...evaluation, status: 'completed' },
      { ...result, problems: { ...result.problems, total: 2 } },
    ),
    { kind: 'incomplete', recorded_units: 2, expected_units: 4 },
  )
  for (const status of ['pending', 'running']) {
    assert.equal(
      resultAvailability({ ...evaluation, status }, { ...result, status }).kind,
      'partial',
    )
  }
  assert.equal(
    resultAvailability(
      { ...evaluation, status: 'completed' },
      { ...result, problems: { ...result.problems, total: 0 } },
    ).kind,
    'empty',
  )
})

test('请求未得到结果、两接口状态不一致或未知状态不伪装空或最终结果', () => {
  assert.deepEqual(resultAvailability(evaluation, undefined), {
    kind: 'unknown',
    recorded_units: null,
    expected_units: 4,
  })
  assert.equal(resultAvailability(evaluation, null).kind, 'unknown')
  assert.equal(
    resultAvailability(
      { ...evaluation, status: 'future' },
      { ...result, status: 'future' },
    ).kind,
    'unknown',
  )
  assert.equal(
    resultAvailability(
      { ...evaluation, status: 'completed' },
      { ...result, status: 'running' },
    ).kind,
    'unknown',
  )
})

test('null度量显示未知，零值与秒/USD单位保留，成功率转百分比', () => {
  assert.equal(metricLabel(null), '未知')
  assert.equal(metricLabel(Infinity, '秒'), '未知')
  assert.equal(metricLabel(0), '0')
  assert.equal(metricLabel(1.25, '秒'), '1.25 秒')
  assert.equal(metricLabel(0, 'USD'), '0 USD')
  assert.equal(successRateLabel(0.25), '25%')
  assert.equal(successRateLabel(null), '未知')
})

test('结果列表状态保持开放值，未知成本明确已知部分且不冒充免费', () => {
  assert.equal(resultStatusLabel('pending'), '待执行')
  assert.equal(resultStatusLabel('completed'), '已完成')
  assert.equal(resultStatusLabel('__proto__'), '未知状态（__proto__）')
  assert.equal(
    resultCostLabel({ estimated_cost_usd: 0, unknown_cost_count: 0 }),
    '0 USD',
  )
  assert.equal(
    resultCostLabel({ estimated_cost_usd: 0, unknown_cost_count: 2 }),
    '2 条成本未知',
  )
  assert.equal(
    resultCostLabel({ estimated_cost_usd: 0.12, unknown_cost_count: 1 }),
    '已知估算 0.12 USD；1 条成本未知',
  )
})

// Catches non-final zero results mislabeled empty and stopped jobs mislabeled partial.
test('任务状态×记录存在性矩阵独立于当前页，只有completed可为最终结果', () => {
  const cases = [
    ['pending', 0, 'waiting'],
    ['pending', 2, 'partial'],
    ['running', 0, 'waiting'],
    ['running', 2, 'partial'],
    ['paused', 0, 'paused'],
    ['paused', 2, 'paused'],
    ['failed', 0, 'failed'],
    ['failed', 2, 'failed'],
    ['cancelled', 0, 'cancelled'],
    ['cancelled', 2, 'cancelled'],
    ['completed', 0, 'empty'],
    ['completed', 2, 'incomplete'],
    ['completed', 4, 'complete'],
  ] as const
  for (const [status, total, kind] of cases) {
    assert.deepEqual(
      resultAvailability(
        { ...evaluation, status },
        { ...result, status, problems: { ...result.problems, total } },
      ),
      { kind, recorded_units: total, expected_units: 4 },
      `${status}/${total}`,
    )
  }
})
