import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createExperimentClient } from './client.ts'
import type { ExperimentJob } from './types.ts'

const job: ExperimentJob = {
  id: 'exp-1',
  name: '对比实验',
  status: 'pending',
  config: {
    name: '对比实验',
    dataset_path: 'datasets/demo.json',
    models: [{ model: 'model-a', temperature: 0.7 }],
    strategies: [{ name: 'direct' }],
    repeats: 1,
    budget: { max_calls: 10 },
    execution: 'serial',
    max_workers: 4,
    api_key_id: 'k1',
  },
  error_message: null,
  created_at: '2026-10-22T00:00:00Z',
  updated_at: '2026-10-22T00:01:00Z',
}

function clientFor(reply: (config: Record<string, unknown>) => unknown) {
  const seen: Array<Record<string, unknown>> = []
  const client = createExperimentClient({
    get: async (url: string, config: Record<string, unknown>) => {
      seen.push({ method: 'GET', url, ...config })
      return (reply({ method: 'GET', url }) as { data: unknown }).data
    },
    post: async (url: string, body?: unknown) => {
      seen.push({ method: 'POST', url, body })
      return (reply({ method: 'POST', url, body }) as { data: unknown }).data
    },
    delete: async (url: string) => {
      seen.push({ method: 'DELETE', url })
      return undefined
    },
  } as never) as ReturnType<typeof createExperimentClient>
  return { client, seen }
}

test('列表与详情走严格解析，模型数与策略数来自 config', async () => {
  const { client, seen } = clientFor(({ url, method }) => {
    if (method === 'GET' && url === '/experiments')
      return {
        data: {
          items: [job],
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      }
    return { data: job }
  })
  const page = await client.list({ status: 'pending', limit: 20, offset: 0 })
  assert.equal(page.total, 1)
  assert.equal(page.items[0].config.models.length, 1)
  assert.equal(page.items[0].config.strategies.length, 1)
  assert.equal(page.items[0].config.budget?.max_calls, 10)
  assert.equal(seen[0].url, '/experiments')
  const detail = await client.get('exp-1')
  assert.equal(detail.id, 'exp-1')
})

test('缺字段或错类型明确拒绝，不造默认值', async () => {
  const broken = { ...job }
  delete (broken as Partial<ExperimentJob>).status
  const { client } = clientFor(() => ({ data: broken }))
  await assert.rejects(client.get('exp-1'), /实验接口响应格式不兼容/)
})

test('run 返回 202 数据并携带 task_id', async () => {
  const { client } = clientFor(() => ({ data: { ...job, task_id: 'task-9' } }))
  const started = await client.run('exp-1')
  assert.equal(started.task_id, 'task-9')
  assert.equal(started.status, 'pending')
})

test('删除走 DELETE 且不解析响应体', async () => {
  const { client, seen } = clientFor(() => undefined)
  await client.remove('exp-1')
  assert.equal(seen[0].method, 'DELETE')
  assert.equal(seen[0].url, '/experiments/exp-1')
})

test('任务快照解析 progress 形状，取消任务走任务通道', async () => {
  const { client, seen } = clientFor(({ url, method }) => {
    if (method === 'GET' && url === '/tasks/task-9')
      return {
        data: {
          id: 'task-9',
          task_type: 'experiment',
          entity_id: 'exp-1',
          celery_task_id: 'celery-1',
          status: 'running',
          progress: {
            current: 3,
            total: 10,
            percentage: 30,
            current_step: 'model-a × direct',
          },
          error_message: null,
          created_at: '2026-10-22T00:00:00Z',
          started_at: null,
          completed_at: null,
          updated_at: '2026-10-22T00:01:00Z',
        },
      }
    if (method === 'GET' && url === '/tasks')
      return {
        data: {
          items: [
            {
              id: 'task-9',
              task_type: 'experiment',
              entity_id: 'exp-1',
              celery_task_id: 'celery-1',
              status: 'running',
              progress: null,
              error_message: null,
              created_at: '2026-10-22T00:00:00Z',
              started_at: null,
              completed_at: null,
              updated_at: '2026-10-22T00:01:00Z',
            },
          ],
          total: 1,
          limit: 100,
          offset: 0,
          has_more: false,
        },
      }
    return undefined
  })
  const snapshot = await client.task('task-9')
  assert.equal(snapshot.progress?.percentage, 30)
  assert.equal(snapshot.progress?.current_step, 'model-a × direct')
  await client.cancelTask('task-9')
  assert.ok(
    seen.some((c) => c.method === 'DELETE' && c.url === '/tasks/task-9'),
  )
  const running = await client.runningExperimentTasks()
  assert.equal(running.length, 1)
  assert.equal(running[0].entity_id, 'exp-1')
})

test('对比报告严格解析嵌套矩阵与显著性，p 值可空', async () => {
  const { client } = clientFor(() => ({
    data: {
      generated_at: '2026-10-22T00:00:00Z',
      experiment: { experiment_id: 'exp-1', name: '对比实验' },
      combinations: [
        {
          combo_id: 'c1',
          model: 'model-a',
          strategy: 'direct',
          repeat: 1,
          token_budget_unsupported: false,
          denominator: { total: 2, completed: 2, budget_exhausted: 0 },
          solved: 1,
          pass_rate_over_total: 0.5,
          pass_rate_over_completed: 0.5,
          formal: { evaluable: 1, solved: 1, rate: 1 },
          sample_validation: { validated: 2, completed: 2, rate: 1 },
          failure_categories: {},
          fix_rate: { opportunities: 0, fixed: 0, rate: 0 },
          actual_consumption: {
            calls: 4,
            prompt_tokens: 100,
            completion_tokens: 50,
            reasoning_tokens: 0,
            total_tokens: 150,
            elapsed_seconds: 1.5,
            avg_calls_per_problem: 2,
            avg_tokens_per_problem: 75,
          },
          cost: { total_cost_usd: 0.02, known: true },
          by_difficulty: {},
          by_tags: {},
        },
      ],
      model_comparison: {
        strategies: {
          direct: {
            matrix: [
              {
                model: 'model-a',
                solved: 1,
                against: {
                  'model-b': { wins: 1, ties: 0, losses: 0, win_rate: 1 },
                },
              },
            ],
            significance: [
              {
                discordant_pairs: 0,
                p_value: null,
                significant: null,
                note: '样本不足，无法检验',
              },
            ],
          },
        },
        cost_effectiveness: [
          {
            model: 'model-a',
            solved: 1,
            total_cost_usd: 0.02,
            solved_per_usd: 50,
          },
        ],
      },
    },
  }))
  const report = await client.comparison('exp-1')
  assert.equal(report.experiment.experiment_id, 'exp-1')
  assert.equal(report.combinations[0].formal.rate, 1)
  assert.equal(report.combinations[0].cost.total_cost_usd, 0.02)
  const group = report.model_comparison.strategies.direct
  assert.equal(group.matrix[0].against['model-b'].win_rate, 1)
  assert.equal(group.significance[0].p_value, null)
  assert.equal(group.significance[0].significant, null)
  assert.equal(group.significance[0].a, undefined)
  assert.equal(report.model_comparison.cost_effectiveness[0].solved_per_usd, 50)
})

test('帕累托与成本建议解析前沿点与三目标推荐', async () => {
  const comparisonPayload = { marker: 'comparison' }
  const { client, seen } = clientFor(({ url }) => {
    if (url === '/pareto/analyze')
      return {
        data: {
          accuracy_metric: 'overall',
          points: [
            {
              id: 'p1',
              model: 'model-a',
              strategy: 'direct',
              repeats: 1,
              mean_cost_usd: 0.02,
              mean_accuracy: 0.5,
              expected_solved_per_usd: 25,
              pareto_optimal: true,
              dominated_by: [],
            },
          ],
          frontier_ids: ['p1'],
          best_value: { feasible: true, point_id: 'p1', basis: '性价比最高' },
          budget_recommendations: [
            { budget_usd: 0.05, feasible: true, point_id: 'p1' },
          ],
        },
      }
    if (url === '/optimize')
      return {
        data: {
          generated_at: '2026-10-22T00:00:00Z',
          selected_objective: 'best_value',
          ranking: {
            ranking: [
              {
                model: 'model-a',
                strategy: 'direct',
                accuracy: 0.5,
                cost_usd: 0.02,
                ratio: 25,
              },
            ],
            excluded: [],
          },
          recommendations: {
            highest_accuracy: {
              objective: 'highest_accuracy',
              feasible: false,
              note: '无可用的成本已知组合',
            },
            best_value: {
              objective: 'best_value',
              feasible: true,
              basis: '性价比最高',
              model: 'model-a',
              strategy: 'direct',
              accuracy: 0.5,
              cost_usd: 0.02,
              ratio: 25,
            },
            lowest_cost: {
              objective: 'lowest_cost',
              feasible: true,
              basis: '满足最低准确率 0% 的组合中成本最低',
              model: 'model-a',
              strategy: 'direct',
              accuracy: 0.5,
              cost_usd: 0.02,
              ratio: 25,
            },
          },
        },
      }
    return undefined
  })
  const pareto = await client.pareto([comparisonPayload], [0.05], 'overall')
  assert.deepEqual(pareto.frontier_ids, ['p1'])
  assert.equal(pareto.points[0].pareto_optimal, true)
  const advisory = await client.optimize(comparisonPayload, {
    minAccuracy: 0,
    objective: 'best_value',
  })
  assert.equal(advisory.recommendations.best_value.model, 'model-a')
  assert.equal(advisory.ranking.ranking[0].ratio, 25)
  assert.ok(seen.some((c) => c.url === '/optimize'))
})
