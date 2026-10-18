import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateLogin } from './loginForm.ts'

test('用户名或邮箱为空', () => {
  const errors = validateLogin({
    identity: '',
    password: 'long-enough-password',
  })
  assert.equal(errors.identity, '请输入用户名或邮箱')
  assert.equal(errors.password, undefined)
})

test('密码为空', () => {
  const errors = validateLogin({ identity: 'ada', password: '' })
  assert.equal(errors.password, '请输入密码')
  assert.equal(errors.identity, undefined)
})

test('两项都为空时同时提示', () => {
  const errors = validateLogin({ identity: '', password: '' })
  assert.equal(errors.identity, '请输入用户名或邮箱')
  assert.equal(errors.password, '请输入密码')
})

test('超过长度上限', () => {
  const errors = validateLogin({
    identity: 'a'.repeat(255),
    password: 'b'.repeat(1025),
  })
  assert.equal(errors.identity, '用户名或邮箱不能超过 254 个字符')
  assert.equal(errors.password, '密码不能超过 1024 个字符')
})

test('合法输入没有错误', () => {
  assert.deepEqual(
    validateLogin({
      identity: 'ada@example.com',
      password: 'long-enough-password',
    }),
    {},
  )
  assert.deepEqual(
    validateLogin({ identity: 'a'.repeat(254), password: 'b'.repeat(1024) }),
    {},
  )
})
