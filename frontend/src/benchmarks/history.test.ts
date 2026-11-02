import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  readHistoryQuery,
  historySearch,
  uniqueActiveRun,
  assertRunAssociation,
  assertTaskAssociation,
} from './history.ts'

test('explicit selection survives filters and pages and preserves unrelated parameters', () => {
  const old = new URLSearchParams(
    'run_id=older&status=failed&offset=40&view=compact',
  )
  const changed = historySearch(old, { status: 'paused', offset: 0 })
  assert.deepEqual(readHistoryQuery(changed), {
    runId: 'older',
    invalidRun: false,
    status: 'paused',
    offset: 0,
    limit: 20,
  })
  assert.equal(changed.get('view'), 'compact')
  assert.equal(
    historySearch(changed, { runId: 'run/a' }).get('run_id'),
    'run/a',
  )
})
test('invalid explicit IDs are reported and invalid pagination is normalized', () => {
  assert.equal(
    readHistoryQuery(new URLSearchParams('run_id=&offset=-1')).invalidRun,
    true,
  )
  assert.equal(
    readHistoryQuery(new URLSearchParams('run_id=a&run_id=b')).invalidRun,
    true,
  )
  assert.equal(
    readHistoryQuery(new URLSearchParams('offset=1e4&status=garbage')).offset,
    0,
  )
  assert.equal(
    readHistoryQuery(new URLSearchParams('offset=1e4&status=garbage')).status,
    undefined,
  )
})
test('auto restore requires exactly one active run across all three successful queries', () => {
  const page = (total: number, id = 'active') => ({
    items: total ? [{ id }] : [],
    total,
    limit: 20,
    offset: 0,
    has_more: total > 20,
  })
  assert.equal(uniqueActiveRun([page(0), page(1), page(0)] as never), 'active')
  assert.equal(uniqueActiveRun([page(21), page(0), page(0)] as never), null)
  assert.equal(uniqueActiveRun([page(1), page(1), page(0)] as never), null)
})
test('run and task association rejects a mismatched suite or unrelated task type/entity', () => {
  assert.doesNotThrow(() =>
    assertRunAssociation({ id: 'r', suite_id: 's' } as never, 's', 'r'),
  )
  assert.throws(() =>
    assertRunAssociation({ id: 'r', suite_id: 'other' } as never, 's', 'r'),
  )
  assert.doesNotThrow(() =>
    assertTaskAssociation(
      { id: 't', entity_id: 'r', task_type: 'benchmark' } as never,
      't',
      'r',
    ),
  )
  assert.throws(() =>
    assertTaskAssociation(
      { id: 't', entity_id: 'other', task_type: 'benchmark' } as never,
      't',
      'r',
    ),
  )
  assert.throws(() =>
    assertTaskAssociation(
      { id: 't', entity_id: 'r', task_type: 'evaluation' } as never,
      't',
      'r',
    ),
  )
})
