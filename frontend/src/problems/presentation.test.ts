import assert from 'node:assert/strict'
import { test } from 'node:test'
import { historyStatusLabel } from './presentation.ts'

test('评估历史状态标签与后端单元状态口径一致', () => {
  // 后端写入的状态值（src/strategy_base.py、src/sandbox_executor.py）。
  assert.equal(historyStatusLabel('success'), '通过')
  assert.equal(historyStatusLabel('failed'), '未通过')
  assert.equal(historyStatusLabel('error'), '执行错误')
  assert.equal(historyStatusLabel('timeout'), '执行超时')
  assert.equal(historyStatusLabel('unsupported'), '不支持')
  assert.equal(historyStatusLabel('budget_exhausted'), '预算跳过')
  assert.equal(historyStatusLabel('not_evaluable'), '不可评估（缺少测试用例）')
  // 未知状态原样展示，不伪装成已通过。
  assert.equal(historyStatusLabel('mystery'), 'mystery')
})
