import assert from 'node:assert/strict'
import { test } from 'node:test'
import { loginWelcome } from './loginWelcome.ts'

test('有用户名时欢迎文案包含用户名', () => {
  assert.equal(loginWelcome('ada'), '欢迎回来，ada')
})

test('用户名中的 HTML 被转义', () => {
  assert.equal(loginWelcome('<b>'), '欢迎回来，&lt;b&gt;')
})

test('没有用户名时只显示欢迎回来', () => {
  assert.equal(loginWelcome(null), '欢迎回来')
  assert.equal(loginWelcome(''), '欢迎回来')
})
