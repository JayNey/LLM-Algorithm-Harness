import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  groupApiKeys,
  lastUsedLabel,
  readApiKeys,
  rejectApiKey,
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
