import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatPercent, formatRatio } from './presentation.ts'

test('百分比与比值格式化：0–100 直排，0–1 比值换算为百分比', () => {
  // 0–100 的资源占用字段保持直排。
  assert.equal(formatPercent(50), '50%')
  assert.equal(formatPercent(25.55), '25.6%')
  assert.equal(formatPercent(null), '—')
  // 监控端点的比率字段是 0–1，需要换算。
  assert.equal(formatRatio(0.95), '95%')
  assert.equal(formatRatio(0.8), '80%')
  assert.equal(formatRatio(0.025), '2.5%')
  assert.equal(formatRatio(null), '—')
})
