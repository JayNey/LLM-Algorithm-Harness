import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  createPayload,
  readListQuery,
  validateDraft,
  writeListQuery,
} from './validation.ts'
import type { Draft, DraftAvailable } from './types.ts'

const draft: Draft = {
  api_key_id: ' k1 ',
  model: ' model-a ',
  problem_ids: ['p1', 'p2', 'p1'],
  strategy_names: ['direct', 'direct'],
  budget_cap_usd: '',
}
const available: DraftAvailable = {
  api_key_ids: ['k1'],
  models: ['model-a'],
  problem_ids: ['p1', 'p2'],
  strategy_names: ['direct'],
}

test('创建载荷去重并只发送真实契约字段，空预算不转成零', () => {
  assert.deepEqual(createPayload(draft), {
    api_key_id: 'k1',
    model: 'model-a',
    problem_ids: ['p1', 'p2'],
    strategy_names: ['direct'],
  })
  assert.deepEqual(createPayload({ ...draft, budget_cap_usd: '0' }), {
    api_key_id: 'k1',
    model: 'model-a',
    problem_ids: ['p1', 'p2'],
    strategy_names: ['direct'],
    budget_cap_usd: 0,
  })
  assert.equal(
    createPayload({ ...draft, budget_cap_usd: ' 1.25 ' }).budget_cap_usd,
    1.25,
  )
})

test('草稿允许已核实的跨页题目和重复选择，拒绝空白与失效选择', () => {
  assert.deepEqual(validateDraft(draft, available), {})
  const errors = validateDraft(
    {
      ...draft,
      api_key_id: ' ',
      model: 'removed',
      problem_ids: ['missing'],
      strategy_names: [],
    },
    available,
  )
  assert.deepEqual(Object.keys(errors).sort(), [
    'api_key_id',
    'model',
    'problem_ids',
    'strategy_names',
  ])
  for (const field of [
    'api_key_id',
    'model',
    'problem_ids',
    'strategy_names',
  ] as const) {
    const value =
      field === 'problem_ids' || field === 'strategy_names' ? [' '] : ' '
    assert.ok(validateDraft({ ...draft, [field]: value }, available)[field])
    assert.throws(() => createPayload({ ...draft, [field]: value }))
  }
  assert.ok(
    validateDraft(
      { ...draft, api_key_id: 'deleted', strategy_names: ['unknown'] },
      available,
    ).api_key_id,
  )
  assert.ok(
    validateDraft({ ...draft, strategy_names: ['unknown'] }, available)
      .strategy_names,
  )
})

test('预算必须有限且非负，校验与载荷拒绝同一无效输入', () => {
  for (const budget_cap_usd of [
    'Infinity',
    '-Infinity',
    'NaN',
    '-1',
    'abc',
    '1e999',
  ]) {
    assert.ok(
      validateDraft({ ...draft, budget_cap_usd }, available).budget_cap_usd,
      budget_cap_usd,
    )
    assert.throws(
      () => createPayload({ ...draft, budget_cap_usd }),
      budget_cap_usd,
    )
  }
  assert.deepEqual(
    validateDraft({ ...draft, budget_cap_usd: ' ' }, available),
    {},
  )
})

test('URL分页先规范化，状态只接受受支持筛选值', () => {
  assert.deepEqual(
    readListQuery(
      new URLSearchParams('status=paused&limit=100&offset=40&sort=name'),
    ),
    { status: 'paused', limit: 100, offset: 40 },
  )
  assert.deepEqual(
    readListQuery(new URLSearchParams('status=future&limit=101&offset=-1')),
    { limit: 20, offset: 0 },
  )
  for (const value of ['', 'NaN', 'Infinity', '1.5', '1e2']) {
    assert.equal(
      readListQuery(new URLSearchParams(`offset=${value}`)).offset,
      0,
    )
  }
  for (const value of ['0', '-2', '1.2', 'abc']) {
    assert.equal(readListQuery(new URLSearchParams(`limit=${value}`)).limit, 20)
  }
  assert.equal(
    writeListQuery({ status: 'running', limit: 20, offset: 40 }).toString(),
    'status=running&limit=20&offset=40',
  )
  assert.equal(
    writeListQuery({
      status: 'unknown',
      limit: Infinity,
      offset: -2,
    }).toString(),
    'limit=20&offset=0',
  )
})

test('刷新与历史导航可还原每个列表筛选和分页，不引入名称搜索参数', () => {
  for (const status of [
    undefined,
    'pending',
    'running',
    'paused',
    'completed',
    'failed',
    'cancelled',
  ]) {
    for (const offset of [0, 20, 40]) {
      const query = { ...(status ? { status } : {}), limit: 20, offset }
      const url = writeListQuery(query)
      assert.deepEqual(
        readListQuery(new URLSearchParams(url.toString())),
        query,
      )
      assert.deepEqual(
        [...url.keys()].sort(),
        (status ? ['limit', 'offset', 'status'] : ['limit', 'offset']).sort(),
      )
    }
  }
})
