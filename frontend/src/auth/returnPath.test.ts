import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sanitizeReturnPath } from './returnPath.ts'

test('保留站内题目路径', () => {
  assert.equal(sanitizeReturnPath('/problems'), '/problems')
})

test('拒绝外站地址和协议相对地址', () => {
  assert.equal(sanitizeReturnPath('https://evil.example/steal'), '/')
  assert.equal(sanitizeReturnPath('//evil.example'), '/')
  assert.equal(sanitizeReturnPath(null), '/')
})
