import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import type { ExperimentDraft } from './types.ts'
import {
  createExperimentPayload,
  readListQuery,
  validateExperimentDraft,
  writeListQuery,
} from './validation.ts'

function draft(overrides: Partial<ExperimentDraft> = {}): ExperimentDraft {
  return {
    name: '',
    dataset_path: 'datasets/demo.json',
    api_key_id: 'k1',
    models: [{ model: 'model-a', temperature: '', api_key_id: '' }],
    strategies: [{ name: 'direct', max_iterations: '', temperature: '' }],
    repeats: '1',
    execution: 'serial',
    max_workers: '4',
    budget_kind: 'none',
    budget_value: '',
    ...overrides,
  }
}

test('合法草稿产出与后端 schema 对齐的 payload', () => {
  const payload = createExperimentPayload(
    draft({
      name: '对比实验',
      repeats: '2',
      execution: 'parallel',
      max_workers: '8',
      budget_kind: 'max_calls',
      budget_value: '50',
      models: [{ model: 'model-a', temperature: '0.5', api_key_id: 'k2' }],
      strategies: [{ name: 'direct', max_iterations: '3', temperature: '0.7' }],
    }),
  )
  assert.equal(payload.name, '对比实验')
  assert.equal(payload.repeats, 2)
  assert.equal(payload.execution, 'parallel')
  assert.equal(payload.max_workers, 8)
  assert.deepEqual(payload.budget, { max_calls: 50 })
  assert.deepEqual(payload.models, [
    { model: 'model-a', temperature: 0.5, api_key_id: 'k2' },
  ])
  assert.deepEqual(payload.strategies, [
    { name: 'direct', max_iterations: 3, temperature: 0.7 },
  ])
})

test('非法草稿指出具体字段且 createPayload 拒绝', () => {
  const errors = validateExperimentDraft(
    draft({
      dataset_path: '  ',
      api_key_id: '',
      models: [{ model: '', temperature: '', api_key_id: '' }],
      strategies: [{ name: '', max_iterations: '', temperature: '' }],
      repeats: '0',
      max_workers: '17',
      budget_kind: 'max_tokens',
      budget_value: '-1',
    }),
  )
  assert.ok(errors.dataset_path)
  assert.ok(errors.api_key_id)
  assert.ok(errors.models)
  assert.ok(errors.strategies)
  assert.ok(errors.repeats)
  assert.ok(errors.max_workers)
  assert.ok(errors.budget_value)
  assert.throws(
    () => createExperimentPayload(draft({ repeats: '0' })),
    ApiClientError,
  )
})

test('空模型被过滤、预算 none 时为 null、温度越界报错', () => {
  const payload = createExperimentPayload(
    draft({
      models: [
        { model: 'model-a', temperature: '', api_key_id: '' },
        { model: '  ', temperature: '', api_key_id: '' },
      ],
    }),
  )
  assert.equal(payload.models.length, 1)
  assert.equal(payload.budget, null)
  assert.ok(
    validateExperimentDraft(
      draft({ models: [{ model: 'm', temperature: '3', api_key_id: '' }] }),
    ).models,
  )
})

test('列表查询白名单回填：非法状态丢弃、limit 钳位', () => {
  const read = readListQuery(
    new URLSearchParams({ status: 'bogus', limit: '500', offset: '-4' }),
  )
  assert.equal(read.status, undefined)
  assert.equal(read.limit, 20)
  assert.equal(read.offset, 0)
  const query = readListQuery(
    new URLSearchParams({ status: 'running', limit: '50' }),
  )
  const search = writeListQuery(query)
  assert.equal(search.get('status'), 'running')
  assert.equal(search.get('limit'), '50')
  assert.equal(search.get('offset'), '0')
})
