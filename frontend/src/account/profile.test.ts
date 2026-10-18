import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatUnixSeconds, readProfile, validateProfile } from './profile.ts'

test('无法识别的资料不被当成一份资料', () => {
  assert.equal(readProfile(null), null)
  assert.equal(readProfile({ username: 'ada', email: 'ada@example.com' }), null)
  assert.equal(
    readProfile({ username: 1, email: 'ada@example.com', created_at: 0 }),
    null,
  )
})

test('资料只保留用户名、邮箱和注册时间', () => {
  assert.deepEqual(
    readProfile({
      id: 'user-1',
      username: 'ada',
      email: 'ada@example.com',
      created_at: 0,
      password_hash: 'hidden',
    }),
    { username: 'ada', email: 'ada@example.com', created_at: 0 },
  )
})

test('注册时间格式化为本地日期而不是裸整数', () => {
  const text = formatUnixSeconds(0)
  assert.notEqual(text, '0')
  assert.match(text, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
})

test('含空格的用户名不合法', () => {
  const errors = validateProfile({
    username: 'ada lovelace',
    email: 'ada@example.com',
  })
  assert.equal(
    errors.username,
    '用户名需为 3–64 个字母、数字、下划线、点或连字符',
  )
  assert.equal(errors.email, undefined)
})
