import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiClientError } from '../auth/http.ts'
import { createExperimentCreationStore } from './runCreation.ts'
import type { ExperimentClient, ExperimentJob } from './types.ts'

const job: ExperimentJob = {
  id: 'exp-new',
  name: '实验',
  status: 'pending',
  config: {
    name: '实验',
    dataset_path: 'datasets/demo.json',
    models: [{ model: 'model-a' }],
    strategies: [{ name: 'direct' }],
    repeats: 1,
    budget: null,
    execution: 'serial',
    max_workers: 4,
  },
  error_message: null,
  created_at: '2026-10-22T00:00:00Z',
  updated_at: '2026-10-22T00:00:00Z',
}

function setup(overrides: Partial<ExperimentClient> = {}) {
  const client = {
    create: async () => job,
    ...overrides,
  } as ExperimentClient
  let owner: string | null = 'user-1'
  const store = createExperimentCreationStore({
    client,
    readOwner: () => owner,
  })
  return {
    store,
    setOwner(value: string | null) {
      owner = value
    },
  }
}

const validPatch = {
  dataset_path: 'datasets/demo.json',
  api_key_id: 'k1',
  models: [{ model: 'model-a', temperature: '', api_key_id: '' }],
  strategies: [{ name: 'direct', max_iterations: '', temperature: '' }],
}

test('submit 走 creating→created 并回填实验 ID', async () => {
  const { store } = setup()
  store.getState().setDraft(validPatch)
  await store.getState().submit()
  assert.equal(store.getState().phase, 'created')
  assert.equal(store.getState().experimentId, 'exp-new')
})

test('非法草稿停在 editing 并携带字段错误', async () => {
  const { store } = setup()
  store.getState().setDraft({ dataset_path: '' })
  await store.getState().submit()
  const state = store.getState()
  assert.equal(state.phase, 'editing')
  assert.equal(state.experimentId, null)
  const fields = (state.error as ApiClientError).details as Record<
    string,
    string
  >
  assert.ok(fields.dataset_path)
})

test('网络失败（非 4xx）转入 create-unknown，4xx 回到 editing', async () => {
  const unknown = setup({
    create: async () => {
      throw new Error('network down')
    },
  })
  unknown.store.getState().setDraft(validPatch)
  await unknown.store.getState().submit()
  assert.equal(unknown.store.getState().phase, 'create-unknown')

  const rejected = setup({
    create: async () => {
      throw new ApiClientError('数据集不存在', 400)
    },
  })
  rejected.store.getState().setDraft({ dataset_path: 'datasets/missing.json' })
  await rejected.store.getState().submit()
  assert.equal(rejected.store.getState().phase, 'editing')
  assert.equal(rejected.store.getState().experimentId, null)
})

test('owner 失配时拒写草稿也拒提交', async () => {
  const { store, setOwner } = setup()
  store.getState().setDraft(validPatch)
  setOwner(null)
  store.getState().setDraft({ name: '别人不可写' })
  assert.equal(store.getState().draft.name, '')
  await store.getState().submit()
  assert.equal(store.getState().phase, 'editing')
  assert.equal(store.getState().experimentId, null)
})
