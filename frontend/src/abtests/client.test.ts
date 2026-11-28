import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import type { ABTestDraft, ABTestJob } from './types.ts'
import { createABTestClient } from './client.ts'
import {
  createPayload,
  readListQuery,
  validateABTestDraft,
  writeListQuery,
} from './validation.ts'

const job: ABTestJob = {
  id: 'ab-1',
  name: '提示词对比',
  status: 'completed',
  config: {
    name: '提示词对比',
    dataset_path: 'datasets/demo.json',
    model: { model: 'model-a', temperature: 0.7 },
    strategy: { name: 'vanilla' },
    prompt_variants: [{ id: 'baseline' }, { id: 'treatment' }],
    seed: 42,
    max_workers: 4,
    api_key_id: 'k1',
  },
  error_message: null,
  created_at: '2026-10-23T00:00:00Z',
  updated_at: '2026-10-23T00:05:00Z',
}

function clientFor(
  reply: (config: { method: string; url: string }) => unknown,
) {
  const seen: Array<Record<string, unknown>> = []
  const client = createABTestClient({
    get: async (url: string) => {
      seen.push({ method: 'GET', url })
      return (reply({ method: 'GET', url }) as { data: unknown }).data
    },
    post: async (url: string, body?: unknown) => {
      seen.push({ method: 'POST', url, body })
      return (reply({ method: 'POST', url }) as { data: unknown }).data
    },
    delete: async (url: string) => {
      seen.push({ method: 'DELETE', url })
      return undefined
    },
  } as never)
  return { client, seen }
}

test('列表与详情严格解析 config 子集', async () => {
  const { client, seen } = clientFor(({ url, method }) => {
    if (method === 'GET' && url === '/ab-tests')
      return {
        data: { items: [job], total: 1, limit: 20, offset: 0, has_more: false },
      }
    return { data: job }
  })
  const page = await client.list({ limit: 20, offset: 0 })
  assert.equal(page.items[0].config.prompt_variants.length, 2)
  assert.equal(page.items[0].config.seed, 42)
  const detail = await client.get('ab-1')
  assert.equal(detail.config.model.model, 'model-a')
  assert.equal(seen[0].url, '/ab-tests')
})

test('完成后统计报告解析：ci95 可空、检验三态、失败分类', async () => {
  const { client } = clientFor(() => ({
    data: {
      name: '提示词对比',
      generated_at: '2026-10-23T00:10:00Z',
      variants: [
        { id: 'baseline', description: '原始提示词' },
        { id: 'treatment', description: '改进提示词' },
      ],
      baseline_id: 'baseline',
      treatment_id: 'treatment',
      comparison: {
        sample: {
          baseline: 0.5,
          treatment: 0.75,
          ci95: { difference: 0.25, lower: -0.1, upper: 0.6 },
        },
        formal: {
          baseline: 0.5,
          treatment: 0.8,
          ci95: { difference: null, lower: null, upper: null },
        },
        statistics: {
          categorical_test: 'unavailable',
          p_value: null,
          welch_t_p_value: null,
        },
        elapsed_seconds: { baseline: 6.1, treatment: 6.4 },
        tokens: { baseline: 600, treatment: 600 },
        failure_categories: { baseline: {}, treatment: { wrong_answer: 1 } },
      },
    },
  }))
  const report = await client.results('ab-1')
  assert.equal(report.comparison.sample.treatment, 0.75)
  assert.equal(report.comparison.formal.ci95.difference, null)
  assert.equal(report.comparison.statistics.categorical_test, 'unavailable')
  assert.equal(report.comparison.statistics.p_value, null)
  assert.deepEqual(report.comparison.failure_categories, {
    baseline: {},
    treatment: { wrong_answer: 1 },
  })
  assert.deepEqual(report.comparison.elapsed_seconds, {
    baseline: 6.1,
    treatment: 6.4,
  })
})

test('缺字段或错类型明确拒绝', async () => {
  const broken = { ...job }
  delete (broken as Partial<ABTestJob>).status
  const { client } = clientFor(() => ({ data: broken }))
  await assert.rejects(client.get('ab-1'), /AB 测试接口响应格式不兼容/)
})

const baseDraft = (overrides: Partial<ABTestDraft> = {}): ABTestDraft => ({
  name: '提示词对比',
  dataset_path: 'datasets/demo.json',
  api_key_id: 'k1',
  model: 'model-a',
  model_temperature: '',
  strategy: 'vanilla',
  strategy_max_iterations: '',
  seed: '',
  max_workers: '4',
  variants: [
    {
      id: 'baseline',
      description: '',
      system_prompt: '',
      prefix: '',
      suffix: '',
    },
    {
      id: 'treatment',
      description: '',
      system_prompt: '',
      prefix: '',
      suffix: '',
    },
  ],
  ...overrides,
})

test('合法草稿产出对齐后端 schema 的 payload（seed 默认 42）', () => {
  const payload = createPayload(baseDraft())
  assert.equal(payload.seed, 42)
  assert.equal(payload.prompt_variants.length, 2)
  assert.equal(payload.prompt_variants[0].id, 'baseline')
  assert.equal(payload.max_workers, 4)
  assert.deepEqual(payload.model, { model: 'model-a' })
  assert.deepEqual(payload.strategy, { name: 'vanilla' })
})

test('非法草稿逐字段报错且 createPayload 拒绝', () => {
  const errors = validateABTestDraft(
    baseDraft({
      dataset_path: '',
      api_key_id: '',
      model: '',
      strategy: '',
      seed: '-1',
      max_workers: '21',
      variants: [
        { id: '', description: '', system_prompt: '', prefix: '', suffix: '' },
      ],
    }),
  )
  assert.ok(errors.dataset_path)
  assert.ok(errors.api_key_id)
  assert.ok(errors.model)
  assert.ok(errors.strategy)
  assert.ok(errors.seed)
  assert.ok(errors.max_workers)
  assert.ok(errors.variants)
  assert.throws(() => createPayload(baseDraft({ seed: '-1' })), ApiClientError)
})

test('变体 ID 重复被拒绝', () => {
  const errors = validateABTestDraft(
    baseDraft({
      variants: [
        {
          id: 'same',
          description: '',
          system_prompt: '',
          prefix: '',
          suffix: '',
        },
        {
          id: 'same',
          description: '',
          system_prompt: '',
          prefix: '',
          suffix: '',
        },
      ],
    }),
  )
  assert.equal(errors.variants, '两个变体 ID 不得相同')
})

test('AB 列表查询白名单回填', () => {
  const query = readListQuery(
    new URLSearchParams({ status: 'failed', limit: '10' }),
  )
  const search = writeListQuery(query)
  assert.equal(search.get('status'), 'failed')
  assert.equal(search.get('limit'), '10')
  const bogus = readListQuery(new URLSearchParams({ status: 'nope' }))
  assert.equal(bogus.status, undefined)
})

test('排队任务保留 task_id，未提交配置兼容缺省字段', async () => {
  const queued = { ...job, status: 'pending', task_id: 'task-ab-1' }
  const { client } = clientFor(() => ({ data: queued }))
  assert.equal((await client.get('ab-1')).task_id, 'task-ab-1')
  const legacy = clientFor(() => ({ data: job })).client
  assert.equal((await legacy.get('ab-1')).task_id, null)
})

test('个人题库 A/B 详情解析保留引用，无需路径', async () => {
  const { client } = clientFor(() => ({
    data: {
      ...job,
      config: { ...job.config, dataset_path: null, dataset_id: 'mine' },
    },
  }))
  const detail = await client.get('ab-1')
  assert.equal(detail.config.dataset_id, 'mine')
  assert.equal(detail.config.dataset_path, undefined)
})

test('高级配置经请求保存，保留筛选归一、变体与 seed/并发', async () => {
  const draft = baseDraft({
    strategy: 'self_consistency',
    strategy_temperature: '0',
    strategy_max_tokens: '3456',
    strategy_system_prompt: '  default instructions\n',
    strategy_custom_params: '{"num_candidates":3,"temperature":1.2}',
    problem_filters: {
      difficulty: 'easy',
      tags: 'array，math\narray',
      problem_ids: 'LC.1, CF-2\nLC.1',
      limit: '2',
    },
    seed: '17',
    max_workers: '2',
  })
  draft.variants[1].system_prompt = 'variant override'
  draft.variants[1].prefix = 'prefix'
  draft.variants[1].suffix = 'suffix'
  const payload = createPayload(draft)
  assert.deepEqual(payload.strategy, {
    name: 'self_consistency',
    temperature: 0,
    max_tokens: 3456,
    system_prompt: '  default instructions\n',
    custom_params: { num_candidates: 3, temperature: 1.2 },
  })
  assert.deepEqual(payload.problem_filters, {
    difficulty: 'easy',
    tags: ['array', 'math'],
    problem_ids: ['LC.1', 'CF-2'],
    limit: 2,
  })
  assert.equal(payload.prompt_variants[0].system_prompt, undefined)
  assert.equal(payload.prompt_variants[1].system_prompt, 'variant override')
  assert.equal(payload.prompt_variants[1].prefix, 'prefix')
  assert.equal(payload.prompt_variants[1].suffix, 'suffix')
  assert.equal(payload.seed, 17)
  assert.equal(payload.max_workers, 2)
  const { client, seen } = clientFor(() => ({
    data: { ...job, config: payload },
  }))
  const saved = await client.create(payload)
  assert.deepEqual(seen[0].body, payload)
  assert.deepEqual(saved.config.strategy, payload.strategy)
  assert.deepEqual(saved.config.problem_filters, payload.problem_filters)
})

test('留空高级输入不覆盖继承默认，旧响应仍兼容', async () => {
  const payload = createPayload(
    baseDraft({
      strategy_temperature: ' ',
      strategy_max_tokens: ' ',
      strategy_system_prompt: '\n',
      strategy_custom_params: '{}',
      problem_filters: { tags: ' ,\n', problem_ids: '', limit: '' },
    }),
  )
  assert.deepEqual(payload.strategy, { name: 'vanilla' })
  assert.equal(Object.hasOwn(payload, 'problem_filters'), false)
  const { client } = clientFor(() => ({ data: job }))
  assert.equal((await client.get(job.id)).config.problem_filters, undefined)
})

test('高级配置非法字段逐项拒绝，切换策略重新检查白名单', () => {
  for (const [patch, key] of [
    ...['-0.1', '2.1', 'Infinity'].map((value) => [
      { strategy_temperature: value },
      'strategy_temperature',
    ]),
    ...['99', '8001', '100.5', '-100', 'NaN'].map((value) => [
      { strategy_max_tokens: value },
      'strategies.0.max_tokens',
    ]),
    ...[
      'oops',
      '[]',
      'null',
      '1',
      '{"num_candidates":0}',
      '{"num_candidates":"3"}',
      '{"temperature":3}',
      '{"base_url":"http://localhost"}',
    ].map((value) => [
      { strategy_custom_params: value },
      'strategies.0.custom_params',
    ]),
    ...['0', '-1', '1.5', 'Infinity'].map((value) => [
      { problem_filters: { limit: value } },
      'problem_filters.limit',
    ]),
    [
      { problem_filters: { difficulty: 'expert' } },
      'problem_filters.difficulty',
    ],
  ] as [Partial<ABTestDraft>, string][]) {
    const draft = baseDraft({ strategy: 'self_consistency', ...patch })
    assert.ok(validateABTestDraft(draft)[key], JSON.stringify(patch))
    assert.throws(() => createPayload(draft), ApiClientError)
  }
  const draft = baseDraft({
    strategy: 'self_consistency',
    strategy_custom_params: '{"num_candidates":3}',
  })
  assert.deepEqual(validateABTestDraft(draft), {})
  assert.ok(
    validateABTestDraft({ ...draft, strategy: 'vanilla' })[
      'strategies.0.custom_params'
    ],
  )
  assert.ok(
    validateABTestDraft(
      baseDraft({
        strategy: 'tree_of_thoughts',
        strategy_custom_params: '{"search_strategy":"random"}',
      }),
    )['strategies.0.custom_params'],
  )
})

test('新增响应字段形状错误明确拒绝，基线与模型温度保留', async () => {
  for (const config of [
    { ...job.config, strategy: { name: 'vanilla', max_tokens: '2000' } },
    { ...job.config, strategy: { name: 'vanilla', custom_params: [] } },
    { ...job.config, problem_filters: { tags: 'array' } },
    { ...job.config, problem_filters: { limit: 1.5 } },
  ]) {
    const { client } = clientFor(() => ({ data: { ...job, config } }))
    await assert.rejects(client.get(job.id), /AB 测试接口响应格式不兼容/)
  }
  const { client } = clientFor(() => ({
    data: { ...job, config: { ...job.config, baseline_id: 'treatment' } },
  }))
  const result = await client.get(job.id)
  assert.equal(result.config.baseline_id, 'treatment')
  assert.equal(result.config.model.temperature, 0.7)
})
