import assert from 'node:assert/strict'
import test from 'node:test'
import { runPayload, validateRunDraft } from './validation.ts'
import type { RunDraft } from './types.ts'

const draft = (patch: Partial<RunDraft> = {}): RunDraft => ({
  api_key_id: 'key',
  dataset_path: 'questions.json',
  model: 'offline',
  strategies_text: '',
  budget_cap_usd: '',
  ...patch,
})

test('name-only and empty inputs preserve default omission', () => {
  assert.equal(runPayload(draft()).strategies, undefined)
  const payload = runPayload(
    draft({
      strategies_text: 'vanilla, vanilla，self_consistency',
      strategy_settings: { vanilla: { temperature: ' ', max_tokens: '' } },
      problem_filters: { limit: '', tags: ' , ' },
    }),
  )
  assert.deepEqual(payload.strategies, [
    { name: 'vanilla' },
    { name: 'self_consistency' },
  ])
  assert.equal(payload.problem_filters, undefined)
})

test('complete strategies and filters reach request; removed strategy cannot leak settings', () => {
  const settings = {
    self_consistency: {
      max_iterations: '3',
      temperature: '0',
      max_tokens: '3456',
      system_prompt: '  Follow instructions.  ',
      custom_params: '{"num_candidates":3,"temperature":1.2}',
    },
  }
  const payload = runPayload(
    draft({
      strategies_text: 'self_consistency',
      strategy_settings: settings,
      problem_filters: {
        difficulty: 'easy',
        tags: 'array,math,array',
        problem_ids: 'b\na',
        limit: '2',
      },
    }),
  )
  assert.deepEqual(payload.strategies, [
    {
      name: 'self_consistency',
      max_iterations: 3,
      temperature: 0,
      max_tokens: 3456,
      system_prompt: '  Follow instructions.  ',
      custom_params: { num_candidates: 3, temperature: 1.2 },
    },
  ])
  assert.deepEqual(payload.problem_filters, {
    difficulty: 'easy',
    tags: ['array', 'math'],
    problem_ids: ['b', 'a'],
    limit: 2,
  })
  assert.deepEqual(
    runPayload(
      draft({ strategies_text: 'vanilla', strategy_settings: settings }),
    ).strategies,
    [{ name: 'vanilla' }],
  )
})

test('invalid numeric controls, filters and custom JSON block submission', () => {
  for (const [field, values] of Object.entries({
    max_iterations: ['0', '11', '1.5', '1e0'],
    temperature: ['-1', 'Infinity', '2.1'],
    max_tokens: ['99', '8001', '100.5'],
    custom_params: [
      '[]',
      'null',
      '{',
      '{"num_candidates":0}',
      '{"path":"/tmp"}',
    ],
  })) {
    for (const value of values) {
      const input = draft({
        strategies_text: 'self_consistency',
        strategy_settings: { self_consistency: { [field]: value } },
      })
      assert.ok(
        validateRunDraft(input)[`strategies.0.${field}`],
        `${field}=${value}`,
      )
      assert.throws(() => runPayload(input))
    }
  }
  for (const limit of ['0', '-1', '1.5', 'Infinity', '9007199254740992'])
    assert.ok(
      validateRunDraft(draft({ problem_filters: { limit } }))[
        'problem_filters.limit'
      ],
    )
  assert.ok(
    validateRunDraft(draft({ problem_filters: { difficulty: 'unknown' } }))[
      'problem_filters.difficulty'
    ],
  )
})
