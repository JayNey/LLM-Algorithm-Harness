import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildProblemImportLocation,
  setProblemImportIntent,
  writeProblemListQuery,
} from './validation.ts'

test('全局导入深链保留当前题库筛选', () => {
  assert.equal(
    buildProblemImportLocation(
      '/problems',
      '?source=personal&limit=10&offset=20',
    ),
    '/problems?source=personal&limit=10&offset=20&import=1',
  )
})

test('从其他页面进入导入时只携带导入意图', () => {
  assert.equal(
    buildProblemImportLocation('/results/run-1', '?page=3'),
    '/problems?import=1',
  )
})

test('关闭导入只清除 import 参数', () => {
  const next = setProblemImportIntent(
    new URLSearchParams('source=personal&limit=10&import=1'),
    false,
  )
  assert.equal(next.toString(), 'source=personal&limit=10')
})

test('列表筛选更新时保留打开的导入面板意图', () => {
  const next = writeProblemListQuery(
    { source: 'shared', limit: 25, offset: 50 },
    new URLSearchParams('source=personal&import=1'),
  )
  assert.equal(next.toString(), 'source=shared&limit=25&offset=50&import=1')
})
