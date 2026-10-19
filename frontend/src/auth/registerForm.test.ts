import assert from 'node:assert/strict'
import { test } from 'node:test'
import { passwordStrength, validateRegistration } from './registerForm.ts'

test('密码不足 12 位不能提交', () => {
  const errors = validateRegistration({
    username: 'ada',
    email: 'ada@example.com',
    password: 'short-pass',
    confirmPassword: 'short-pass',
  })
  assert.equal(errors.password, '至少 12 个字符')
})

test('确认密码不一致', () => {
  const errors = validateRegistration({
    username: 'ada',
    email: 'ada@example.com',
    password: 'long-enough-password',
    confirmPassword: 'different-password',
  })
  assert.equal(errors.confirmPassword, '两次密码不一致')
})

test('长度分档', () => {
  assert.equal(passwordStrength('short'), 'short')
  assert.equal(passwordStrength('long-enough-pw'), 'ok')
  assert.equal(passwordStrength('sixteen-chars!!!'), 'long')
})

test('12 到 15 位密码为 ok', () => {
  assert.equal(passwordStrength('a'.repeat(12)), 'ok')
  assert.equal(passwordStrength('a'.repeat(15)), 'ok')
  assert.equal(passwordStrength('a'.repeat(11)), 'short')
  assert.equal(passwordStrength('a'.repeat(16)), 'long')
})

test('用户名过短或含非法字符', () => {
  const tooShort = validateRegistration({
    username: 'ab',
    email: 'ada@example.com',
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  const illegal = validateRegistration({
    username: 'bad name',
    email: 'ada@example.com',
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  assert.equal(
    tooShort.username,
    '用户名需为 3–64 个字母、数字、下划线、点或连字符',
  )
  assert.equal(
    illegal.username,
    '用户名需为 3–64 个字母、数字、下划线、点或连字符',
  )
})

test('用户名超过 64 个字符', () => {
  const errors = validateRegistration({
    username: 'a'.repeat(65),
    email: 'ada@example.com',
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  assert.equal(
    errors.username,
    '用户名需为 3–64 个字母、数字、下划线、点或连字符',
  )
})

test('邮箱的点不在域名或含空白、多余 @', () => {
  for (const email of ['a.b@c', 'a@b.', 'a @b.com', 'a@b@c.com']) {
    const errors = validateRegistration({
      username: 'ada',
      email,
      password: 'long-enough-password',
      confirmPassword: 'long-enough-password',
    })
    assert.equal(errors.email, '请输入有效邮箱')
  }
})

test('邮箱缺少 @ 或点', () => {
  const missingAt = validateRegistration({
    username: 'ada',
    email: 'ada.example.com',
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  const missingDot = validateRegistration({
    username: 'ada',
    email: 'ada@examplecom',
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  assert.equal(missingAt.email, '请输入有效邮箱')
  assert.equal(missingDot.email, '请输入有效邮箱')
})

test('邮箱长度超出 3–254', () => {
  const tooLong = validateRegistration({
    username: 'ada',
    email: `${'a'.repeat(250)}@b.co`,
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  const tooShort = validateRegistration({
    username: 'ada',
    email: 'a@',
    password: 'long-enough-password',
    confirmPassword: 'long-enough-password',
  })
  assert.equal(tooLong.email, '请输入有效邮箱')
  assert.equal(tooShort.email, '请输入有效邮箱')
})

test('密码超过 1024 个字符', () => {
  const password = 'p'.repeat(1025)
  const errors = validateRegistration({
    username: 'ada',
    email: 'ada@example.com',
    password,
    confirmPassword: password,
  })
  assert.equal(errors.password, '密码不能超过 1024 个字符')
})

test('合法注册信息没有字段错误', () => {
  const errors = validateRegistration({
    username: 'Ada_1-x.y',
    email: 'ada@example.com',
    password: 'a'.repeat(12),
    confirmPassword: 'a'.repeat(12),
  })
  assert.deepEqual(errors, {})
})
