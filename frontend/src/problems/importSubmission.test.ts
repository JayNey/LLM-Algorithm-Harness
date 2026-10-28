import assert from 'node:assert/strict'
import test from 'node:test'
import { canSubmitImport } from './importSubmission.ts'

test('导入尚未选择文件时不允许提交', () => {
  assert.equal(canSubmitImport(false, false, null), false)
})

test('导入请求进行中时不允许再次提交', () => {
  assert.equal(canSubmitImport(true, true, null), false)
  assert.equal(canSubmitImport(true, false, null, true), false)
})

test('异步导入任务未终态时不允许创建重复任务', () => {
  for (const status of ['pending', 'running', 'paused']) {
    assert.equal(canSubmitImport(true, false, status), false, status)
  }
})

test('导入任务终止后可以开始新的导入', () => {
  for (const status of ['completed', 'failed', 'cancelled']) {
    assert.equal(canSubmitImport(true, false, status), true, status)
  }
})
