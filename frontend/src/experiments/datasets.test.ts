import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createExperimentPayload } from './validation.ts'
import { createPayload } from '../abtests/validation.ts'
import { runPayload } from '../benchmarks/validation.ts'

const source = {
  dataset_id: 'private-dataset',
  dataset_path: '',
  api_key_id: 'key',
}
const experiment = {
  ...source,
  name: '',
  models: [{ model: 'model', temperature: '', api_key_id: '' }],
  strategies: [{ name: 'vanilla', max_iterations: '', temperature: '' }],
  repeats: '1',
  execution: 'serial' as const,
  max_workers: '1',
  budget_kind: 'none' as const,
  budget_value: '',
}
const ab = {
  ...source,
  name: '',
  model: 'model',
  model_temperature: '',
  strategy: 'vanilla',
  strategy_max_iterations: '',
  seed: '42',
  max_workers: '1',
  variants: [
    { id: 'a', description: '', system_prompt: '', prefix: '', suffix: '' },
    { id: 'b', description: '', system_prompt: '', prefix: '', suffix: '' },
  ],
}
const benchmark = {
  ...source,
  model: 'model',
  strategies_text: '',
  budget_cap_usd: '',
}

for (const [name, submit, draft] of [
  ['experiment', createExperimentPayload, experiment],
  ['ab', createPayload, ab],
  ['benchmark', runPayload, benchmark],
] as const) {
  test(`${name}: personal selection sends only dataset_id, rejects conflicting sources`, () => {
    const payload = (submit as (draft: unknown) => Record<string, unknown>)(
      draft,
    )
    assert.equal(payload.dataset_id, source.dataset_id)
    assert.equal('dataset_path' in payload, false)
    assert.throws(() =>
      (submit as (draft: unknown) => unknown)({
        ...draft,
        dataset_path: 'demo.json',
      }),
    )
  })
}

// The server can return new references as well as historical path-based jobs.
test('dataset readers preserve personal and legacy sources and reject ambiguous responses', async () => {
  const { readDatasetSource, readDatasets } = await import('./datasets.ts')
  assert.deepEqual(
    readDatasetSource({ dataset_id: 'mine', dataset_path: null }),
    { dataset_id: 'mine' },
  )
  assert.deepEqual(
    readDatasetSource({ dataset_path: 'demo.json', dataset_id: null }),
    { dataset_path: 'demo.json' },
  )
  assert.throws(() =>
    readDatasetSource({ dataset_id: 'mine', dataset_path: 'other.json' }),
  )
  assert.throws(() => readDatasetSource({ dataset_id: '', dataset_path: null }))
  assert.deepEqual(readDatasets([]), [])
  assert.throws(() =>
    readDatasets([
      { id: 'mine', name: 'Mine', problem_count: -1, updated_at: 0 },
    ]),
  )
})
