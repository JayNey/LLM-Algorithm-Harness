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

test('帕累托与成本建议经原始报告解析前沿点与三目标推荐', async () => {
  const rawComparison = { marker: 'raw-comparison', combinations: [] }
  const { client, seen } = clientFor(({ url, method }) => {
    if (method === 'GET' && url === '/experiments/exp-1/comparison')
      return { data: rawComparison }
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
  const pareto = await client.pareto('exp-1', [0.05], 'overall')
  assert.deepEqual(pareto.frontier_ids, ['p1'])
  assert.equal(pareto.points[0].pareto_optimal, true)
  const advisory = await client.optimize('exp-1', {
    minAccuracy: 0,
    objective: 'best_value',
  })
  assert.equal(advisory.recommendations.best_value.model, 'model-a')
  assert.equal(advisory.ranking.ranking[0].ratio, 25)
  // 帕累托/优化必须上报原始报告（后端校验依赖数据集指纹等未解析字段）
  const paretoCall = seen.find((c) => c.url === '/pareto/analyze')
  assert.deepEqual(
    (paretoCall!.body as { comparisons: unknown[] }).comparisons,
    [rawComparison],
  )
  assert.ok(seen.some((c) => c.url === '/optimize'))
})

test('真实后端形状：比率为 null、无顶层 api_key_id 时照常解析', async () => {
  const { client } = clientFor(() => ({
    data: {
      generated_at: '2026-10-22T00:00:00Z',
      experiment: { experiment_id: 'exp-1', name: 'X' },
      combinations: [
        {
          combo_id: 'c2',
          model: 'model-b',
          strategy: 'direct',
          repeat: 1,
          token_budget_unsupported: true,
          denominator: { total: 3, completed: 0, budget_exhausted: 0 },
          solved: 0,
          pass_rate_over_total: null,
          pass_rate_over_completed: null,
          formal: { evaluable: 0, solved: 0, rate: null },
          sample_validation: { validated: 0, completed: 0, rate: null },
          failure_categories: {},
          fix_rate: { opportunities: 0, fixed: 0, rate: null },
          actual_consumption: {
            calls: 0,
            prompt_tokens: 0,
            completion_tokens: 0,
            reasoning_tokens: 0,
            total_tokens: 0,
            elapsed_seconds: 0,
            avg_calls_per_problem: null,
            avg_tokens_per_problem: null,
          },
          cost: { total_cost_usd: null, known: false },
          by_difficulty: {},
          by_tags: {},
        },
      ],
      model_comparison: {
        strategies: {
          direct: {
            matrix: [
              {
                model: 'model-b',
                solved: 0,
                against: {
                  'model-a': { wins: 0, ties: 0, losses: 0, win_rate: null },
                },
              },
            ],
            significance: [],
          },
        },
        cost_effectiveness: [],
      },
    },
  }))
  const report = await client.comparison('exp-1')
  const row = report.combinations[0]
  assert.equal(row.pass_rate_over_total, null)
  assert.equal(row.formal.rate, null)
  assert.equal(row.token_budget_unsupported, true)
  assert.equal(
    report.model_comparison.strategies.direct.matrix[0].against['model-a']
      .win_rate,
    null,
  )
})

test('详情与列表保留排队 task_id，未入队返回 null，兼容旧响应', async () => {
  for (const task_id of ['queued-task', null, undefined]) {
    const row = { ...job, ...(task_id === undefined ? {} : { task_id }) }
    const { client } = clientFor(({ url }) => ({
      data:
        url === '/experiments'
          ? { items: [row], total: 1, limit: 20, offset: 0, has_more: false }
          : row,
    }))
    assert.equal((await client.get('exp-1')).task_id, task_id)
    assert.equal(
      (await client.list({ limit: 20, offset: 0 })).items[0].task_id,
      task_id,
    )
  }
})

test('错误 task_id 不能被当成未启动的实验', async () => {
  const { client } = clientFor(() => ({ data: { ...job, task_id: 123 } }))
  await assert.rejects(client.get('exp-1'), /实验接口响应格式不兼容/)
})

test('旧接口恢复完整 pending 分页并保留 running、paused 任务', async () => {
  const seen: Array<{ status: string; offset: number }> = []
  const client = createExperimentClient({
    get: async (
      _url: string,
      { params }: { params: { status: string; offset: number } },
    ) => {
      seen.push(params)
      const offset = params.offset ?? 0
      return {
        items: [
          {
            id: `${params.status}-${offset}`,
            task_type: 'experiment',
            entity_id: `exp-${offset}`,
            status: params.status,
            progress: null,
            error_message: null,
            created_at: job.created_at,
            updated_at: job.updated_at,
          },
        ],
        total: params.status === 'pending' ? 2 : 1,
        limit: 1,
        offset,
        has_more: params.status === 'pending' && offset === 0,
      }
    },
  } as never)
  const tasks = await client.runningExperimentTasks()
  assert.deepEqual(tasks.map((task) => task.id).sort(), [
    'paused-0',
    'pending-0',
    'pending-1',
    'running-0',
  ])
  assert.ok(
    seen.some((query) => query.status === 'pending' && query.offset === 1),
  )
})

test('个人题库响应无需 dataset_path 即可读取与展示', async () => {
  const { client } = clientFor(() => ({
    data: {
      ...job,
      config: { ...job.config, dataset_path: null, dataset_id: 'mine' },
    },
  }))
  const detail = await client.get('exp-1')
  assert.equal(detail.config.dataset_id, 'mine')
  assert.equal(detail.config.dataset_path, undefined)
})

test('Pareto 多实验去重并保留原始快照、预算和口径，读取失败不提交部分报告', async () => {
  const snapshots = ['one', 'two'].map((id) => ({
    experiment: { experiment_id: id, dataset: { sha256: 'snapshot' } },
    combinations: [],
  }))
  const result = {
    accuracy_metric: 'formal',
    points: [],
    frontier_ids: [],
    best_value: { feasible: false, point_id: null, basis: '' },
    budget_recommendations: [],
  }
  const { client, seen } = clientFor(({ method, url }) => ({
    data:
      method === 'POST'
        ? result
        : snapshots[url === '/experiments/one/comparison' ? 0 : 1],
  }))
  const signal = new AbortController().signal
  await client.pareto(
    ['one', 'two', 'one'],
    [0, 0.012345, 2, 2],
    'formal',
    signal,
  )
  assert.equal(seen.filter((call) => call.method === 'GET').length, 2)
  assert.ok(
    seen
      .filter((call) => call.method === 'GET')
      .every((call) => call.signal === signal),
  )
  assert.deepEqual(seen.find((call) => call.method === 'POST')?.body, {
    comparisons: snapshots,
    budgets: [0, 0.012345, 2, 2],
    accuracy_metric: 'formal',
  })
  const before = seen.length
  await assert.rejects(client.pareto([], [], 'overall'), /请选择至少一个实验/)
  assert.equal(seen.length, before)
  const failed = clientFor(({ url }) => {
    if (url === '/experiments/two/comparison') throw new Error('access denied')
    return { data: snapshots[0] }
  })
  await assert.rejects(
    failed.client.pareto(['one', 'two'], [], 'overall'),
    /access denied/,
  )
  assert.equal(
    failed.seen.some((call) => call.method === 'POST'),
    false,
  )
  const cancelled = new AbortController()
  cancelled.abort()
  await assert.rejects(
    client.pareto(['one'], [], 'overall', cancelled.signal),
    { name: 'AbortError' },
  )
})

test('高级配置在创建、读取和旧任务响应中保留兼容性', async () => {
  const config = {
    ...job.config,
    strategies: [
      {
        name: 'self_consistency',
        max_iterations: 2,
        temperature: 0.4,
        max_tokens: 3456,
        system_prompt: 'Be precise',
        custom_params: { num_candidates: 3 },
      },
    ],
    problem_filters: {
      difficulty: 'easy',
      tags: ['array'],
      problem_ids: ['one'],
      limit: 1,
    },
    budget: { max_calls: 2, max_tokens: 100, max_seconds: 2.5 },
  }
  const { client, seen } = clientFor(() => ({ data: { ...job, config } }))
  const created = await client.create({ ...config, api_key_id: 'k1' })
  assert.deepEqual(created.config, config)
  assert.deepEqual(
    (seen[0].body as Record<string, unknown>).strategies,
    config.strategies,
  )
  assert.deepEqual((await client.get('exp-1')).config, config)
  const legacy = clientFor(() => ({ data: job })).client
  assert.deepEqual((await legacy.get('exp-1')).config.strategies, [
    { name: 'direct' },
  ])
})

test('新增响应字段形状错误时显式报错', async () => {
  for (const config of [
    { ...job.config, problem_filters: { tags: 'array' } },
    { ...job.config, strategies: [{ name: 'vanilla', custom_params: [] }] },
    { ...job.config, strategies: [{ name: 'vanilla', max_tokens: '2000' }] },
  ]) {
    await assert.rejects(
      clientFor(() => ({ data: { ...job, config } })).client.get('exp-1'),
      /实验接口响应格式不兼容/,
    )
  }
})
