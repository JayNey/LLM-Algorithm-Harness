import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  groupApiKeys,
  lastUsedLabel,
  readApiKey,
  readApiKeys,
  rejectApiKey,
  renamePayload,
  verifyStatusText,
  type ApiKeyRecord,
} from './apiKeys.ts'

function key(overrides: Partial<ApiKeyRecord>): ApiKeyRecord {
  return {
    id: 'k1',
    provider: 'openai',
    key_name: 'primary',
    created_at: 0,
    last_used_at: null,
    usage_count: 0,
    verified: false,
    ...overrides,
  }
}

test('两个提供商分到对应组，空组不出现', () => {
  const groups = groupApiKeys([
    key({ id: 'o', provider: 'openai' }),
    key({ id: 'a', provider: 'anthropic', key_name: 'claude' }),
  ])
  assert.deepEqual(
    groups.map((group) => group.provider),
    ['openai', 'anthropic'],
  )
  assert.equal(
    groups.some((group) => group.provider === 'siliconflow'),
    false,
  )
})

test('没有最后使用时间时表示尚未使用且次数为 0', () => {
  const [group] = groupApiKeys([key({ usage_count: 0, last_used_at: null })])
  const item = group?.keys[0]
  assert.ok(item)
  assert.equal(item.usage_count, 0)
  assert.equal(lastUsedLabel(item.last_used_at), '尚未使用')
  assert.equal(lastUsedLabel(1), null)
})

test('拒绝空白和环境变量引用', () => {
  for (const value of [
    '',
    '   ',
    'env:OPENAI_API_KEY',
    'ENV:TOKEN',
    '${KEY}',
  ]) {
    assert.equal(rejectApiKey(value), '需要真实密钥值')
  }
  assert.equal(rejectApiKey('sk-live'), null)
})

test('整数验证状态解析为布尔且不保留密钥字段', () => {
  const unverified = readApiKey({
    id: 'k1',
    provider: 'openai',
    key_name: 'primary',
    created_at: 1,
    last_used_at: null,
    usage_count: 0,
    verified: 0,
    api_key: 'sk-secret',
  })
  assert.ok(unverified)
  assert.equal(unverified.verified, false)
  assert.equal(Object.hasOwn(unverified, 'api_key'), false)

  const verified = readApiKey({
    id: 'k2',
    provider: 'anthropic',
    key_name: 'claude',
    created_at: 1,
    last_used_at: null,
    usage_count: 0,
    verified: 1,
  })
  assert.equal(verified?.verified, true)
})

test('解析结果不保留密钥字段', () => {
  const parsed = readApiKeys([
    {
      id: 'k1',
      provider: 'openai',
      key_name: 'primary',
      created_at: 1,
      last_used_at: null,
      usage_count: 0,
      verified: false,
      api_key: 'sk-secret',
    },
  ])
  assert.equal(parsed?.[0] && Object.hasOwn(parsed[0], 'api_key'), false)
  assert.equal(readApiKeys({ data: [] }), null)
})

test('改名载荷只有 key_name', () => {
  const payload = renamePayload('renamed')
  assert.deepEqual(payload, { key_name: 'renamed' })
  assert.equal(Object.hasOwn(payload, 'api_key'), false)
})

test('验证文案只有成功或失败', () => {
  assert.equal(verifyStatusText(true), '验证成功')
  assert.equal(verifyStatusText(false), '验证失败')
})
