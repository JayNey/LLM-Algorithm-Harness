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
    strategy: { name: 'direct' },
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
  strategy: 'direct',
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
