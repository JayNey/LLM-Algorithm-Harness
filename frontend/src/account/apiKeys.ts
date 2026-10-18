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

export function readApiKey(value: unknown): ApiKeyRecord | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  const lastUsed = record.last_used_at
  if (
    typeof record.id !== 'string' ||
    !isProvider(record.provider) ||
    typeof record.key_name !== 'string' ||
    typeof record.created_at !== 'number' ||
    typeof record.verified !== 'boolean' ||
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
    verified: record.verified,
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
