import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  effectiveApiKey,
  joinStrategyTags,
  splitStrategyText,
} from './optionCatalog.ts'

test('splitStrategyText 按逗号拆分并修剪空片段', () => {
  assert.deepEqual(splitStrategyText(''), [])
  assert.deepEqual(splitStrategyText('vanilla'), ['vanilla'])
  assert.deepEqual(splitStrategyText('vanilla, chain_of_thought'), [
    'vanilla',
    'chain_of_thought',
  ])
  assert.deepEqual(splitStrategyText(' , vanilla ,, '), ['vanilla'])
})

test('joinStrategyTags 去重并跳过空值，与 split 往返一致', () => {
  assert.equal(joinStrategyTags([]), '')
  assert.equal(joinStrategyTags(['vanilla']), 'vanilla')
  assert.equal(
    joinStrategyTags(['vanilla', ' cot ', '', 'vanilla']),
    'vanilla, cot',
  )
  for (const tags of [['vanilla'], ['a', 'b'], []]) {
    assert.deepEqual(splitStrategyText(joinStrategyTags(tags)), tags)
  }
})

test('effectiveApiKey 专用密钥优先，均修剪，空则回退默认', () => {
  assert.equal(effectiveApiKey(' key-2 ', 'key-1'), 'key-2')
  assert.equal(effectiveApiKey('  ', 'key-1'), 'key-1')
  assert.equal(effectiveApiKey('', '  '), '')
})
