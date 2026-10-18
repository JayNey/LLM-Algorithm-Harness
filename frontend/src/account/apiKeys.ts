export const providers = ['openai', 'anthropic', 'siliconflow'] as const

export type Provider = (typeof providers)[number]

export interface ApiKeyRecord {
  id: string
  provider: Provider
  key_name: string
  created_at: number
  last_used_at: number | null
  usage_count: number
  verified: boolean
}

export interface ApiKeyGroup {
  provider: Provider
  label: string
  keys: ApiKeyRecord[]
}

const labels: Record<Provider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  siliconflow: 'SiliconFlow',
}

function isProvider(value: unknown): value is Provider {
  return providers.includes(value as Provider)
}

function readVerified(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (value === 0) return false
  if (value === 1) return true
  return null
}

export function readApiKey(value: unknown): ApiKeyRecord | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  const lastUsed = record.last_used_at
  const verified = readVerified(record.verified)
  if (
    typeof record.id !== 'string' ||
    !isProvider(record.provider) ||
    typeof record.key_name !== 'string' ||
    typeof record.created_at !== 'number' ||
    verified === null ||
    (lastUsed !== null && typeof lastUsed !== 'number')
  ) {
    return null
  }
  return {
    id: record.id,
    provider: record.provider,
    key_name: record.key_name,
    created_at: record.created_at,
    last_used_at: lastUsed,
    usage_count:
      typeof record.usage_count === 'number' ? record.usage_count : 0,
    verified,
  }
}

export function readApiKeys(value: unknown): ApiKeyRecord[] | null {
  if (!Array.isArray(value)) return null
  const keys: ApiKeyRecord[] = []
  for (const item of value) {
    const key = readApiKey(item)
    if (key) keys.push(key)
  }
  return keys
}

export function groupApiKeys(keys: readonly ApiKeyRecord[]): ApiKeyGroup[] {
  return providers.flatMap((provider) => {
    const matched = keys.filter((key) => key.provider === provider)
    if (matched.length === 0) return []
    return [{ provider, label: labels[provider], keys: matched }]
  })
}

export function lastUsedLabel(lastUsedAt: number | null): string | null {
  return lastUsedAt === null ? '尚未使用' : null
}

export function rejectApiKey(value: string): string | null {
  if (
    value.trim().length === 0 ||
    value.toLowerCase().startsWith('env:') ||
    value.startsWith('${')
  ) {
    return '需要真实密钥值'
  }
  return null
}

export function validateKeyName(name: string): string | null {
  if (name.length < 1 || name.length > 100) return '名称需为 1–100 个字符'
  return null
}

export function renamePayload(keyName: string): { key_name: string } {
  return { key_name: keyName }
}

export function verifyStatusText(ok: boolean): '验证成功' | '验证失败' {
  return ok ? '验证成功' : '验证失败'
}
