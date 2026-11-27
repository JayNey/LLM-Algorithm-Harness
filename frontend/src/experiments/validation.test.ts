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

for (const kind of ['max_calls', 'max_tokens'] as const) {
  test(`${kind} 仅接受正整数预算`, () => {
    for (const value of [
      '1.5',
      '0.5',
      '0',
      '-1',
      'abc',
      '',
      '9007199254740993',
    ]) {
      const invalid = draft({ budget_kind: kind, budget_value: value })
      assert.equal(
        validateExperimentDraft(invalid).budget_value,
        '预算须为正整数',
        value,
      )
      assert.throws(() => createExperimentPayload(invalid), ApiClientError)
    }
    assert.deepEqual(
      createExperimentPayload(
        draft({ budget_kind: kind, budget_value: ' 42 ' }),
      ).budget,
      { [kind]: 42 },
    )
  })
}

test('时间预算保留正小数，无预算时忽略限制值', () => {
  assert.deepEqual(
    createExperimentPayload(
      draft({ budget_kind: 'max_seconds', budget_value: '0.5' }),
    ).budget,
    { max_seconds: 0.5 },
  )
  assert.equal(
    createExperimentPayload(draft({ budget_value: 'abc' })).budget,
    null,
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

test('高级参数与筛选及多维预算完整提交，保留提示词正文', () => {
  const payload = createExperimentPayload(
    draft({
      strategies: [
        {
          name: 'self_consistency',
          max_iterations: '',
          temperature: '',
          max_tokens: '3456',
          system_prompt: '  Explain carefully.\n',
          custom_params: '{"num_candidates":3,"temperature":1.2}',
        },
      ],
      problem_filters: {
        difficulty: 'easy',
        tags: 'array, math\narray',
        problem_ids: 'cf:1-A, lc-2\nlc-2',
        limit: '2',
      },
      budget: { max_calls: '4', max_tokens: '500', max_seconds: '1.5' },
    }),
  )
  assert.deepEqual(payload.strategies, [
    {
      name: 'self_consistency',
      max_tokens: 3456,
      system_prompt: '  Explain carefully.\n',
      custom_params: { num_candidates: 3, temperature: 1.2 },
    },
  ])
  assert.deepEqual(payload.problem_filters, {
    difficulty: 'easy',
    tags: ['array', 'math'],
    problem_ids: ['cf:1-A', 'lc-2'],
    limit: 2,
  })
  assert.deepEqual(payload.budget, {
    max_calls: 4,
    max_tokens: 500,
    max_seconds: 1.5,
  })
})

test('空高级配置保持省略，空新预算覆盖旧单预算', () => {
  const payload = createExperimentPayload(
    draft({
      strategies: [
        {
          name: 'vanilla',
          max_iterations: '',
          temperature: '',
          max_tokens: ' ',
          system_prompt: ' ',
          custom_params: '{}',
        },
      ],
      problem_filters: { tags: ' , \n', limit: ' ' },
      budget: {},
      budget_kind: 'max_calls',
      budget_value: '12',
    }),
  )
  assert.deepEqual(payload.strategies, [{ name: 'vanilla' }])
  assert.equal(payload.problem_filters, undefined)
  assert.equal(payload.budget, null)
})

test('高级错误定位到策略和字段；修正后可提交', () => {
  for (const input of [
    '{',
    '[]',
    'null',
    'true',
    '{"num_candidates":0}',
    '{"num_candidates":1.2}',
    '{"num_candidates":true}',
    '{"temperature":3}',
    '{"base_url":"http://host"}',
    '{"example_manifest":"/private"}',
    '{"__proto__":1}',
  ]) {
    const value = draft({
      strategies: [
        {
          name: 'self_consistency',
          max_iterations: '',
          temperature: '',
          custom_params: input,
        },
      ],
    })
    assert.ok(
      validateExperimentDraft(value)['strategies.0.custom_params'],
      input,
    )
    assert.throws(() => createExperimentPayload(value), ApiClientError)
  }
  for (const value of ['99', '8001', '1.5', 'Infinity']) {
    assert.ok(
      validateExperimentDraft(
        draft({
          strategies: [
            {
              name: 'vanilla',
              max_iterations: '',
              temperature: '',
              max_tokens: value,
            },
          ],
        }),
      )['strategies.0.max_tokens'],
    )
  }
  assert.ok(
    validateExperimentDraft(draft({ problem_filters: { limit: '0' } }))[
      'problem_filters.limit'
    ],
  )
  assert.ok(
    validateExperimentDraft(
      draft({ problem_filters: { difficulty: 'unknown' } }),
    )['problem_filters.difficulty'],
  )
  const invalid = draft({
    budget: { max_calls: '1.5', max_tokens: '-1', max_seconds: 'Infinity' },
  })
  const errors = validateExperimentDraft(invalid)
  for (const key of ['max_calls', 'max_tokens', 'max_seconds'])
    assert.ok(errors[`budget.${key}`])
  invalid.budget = { max_calls: '1', max_tokens: '15', max_seconds: '0.5' }
  assert.deepEqual(validateExperimentDraft(invalid), {})
})

test('白名单覆盖其他现有策略控件及枚举边界', () => {
  const valid = [
    [
      'tree_of_thoughts',
      {
        branching_factor: 1,
        max_depth: 2,
        search_strategy: 'dfs',
        pruning_threshold: 0,
      },
    ],
    [
      'few_shot_learning',
      {
        num_examples: 0,
        similarity_metric: 'tag_overlap',
        min_similarity_score: 1,
      },
    ],
    ['reflexion', { reflection_context_chars: 1 }],
  ] as const
  for (const [name, custom_params] of valid) {
    const input = draft({
      strategies: [
        {
          name,
          max_iterations: '',
          temperature: '',
          custom_params: JSON.stringify(custom_params),
        },
      ],
    })
    assert.deepEqual(
      createExperimentPayload(input).strategies[0].custom_params,
      custom_params,
    )
  }
  for (const [name, params] of [
    ['tree_of_thoughts', { search_strategy: 'random' }],
    ['few_shot_learning', { similarity_metric: 'embedding' }],
    ['reflexion', { reflection_context_chars: 0 }],
    ['vanilla', { num_candidates: 2 }],
  ] as const) {
    assert.ok(
      validateExperimentDraft(
        draft({
          strategies: [
            {
              name,
              max_iterations: '',
              temperature: '',
              custom_params: JSON.stringify(params),
            },
          ],
        }),
      )['strategies.0.custom_params'],
    )
  }
})
