export const REQUIRED_ENV_KEYS = [
  'VITE_API_BASE_URL',
  'VITE_WS_URL',
  'VITE_APP_NAME',
] as const

export interface AppEnv {
  apiBaseUrl: string
  wsUrl: string
  appName: string
  featureFlags: ReadonlySet<string>
}

export function parseEnvFile(text: string): Record<string, string> {
  const values: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (trimmed.length === 0 || trimmed.startsWith('#')) {
      continue
    }
    const separator = trimmed.indexOf('=')
    if (separator === -1) {
      continue
    }
    const key = trimmed.slice(0, separator).trim()
    let value = trimmed.slice(separator + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    values[key] = value
  }
  return values
}

export function readAppEnv(source: Record<string, string | undefined>): AppEnv {
  const missing = REQUIRED_ENV_KEYS.filter((key) => !source[key]?.trim())
  if (missing.length > 0) {
    throw new Error(`缺少环境变量: ${missing.join(', ')}`)
  }

  const flags = (source.VITE_FEATURE_FLAGS ?? '')
    .split(',')
    .map((flag) => flag.trim())
    .filter((flag) => flag.length > 0)

  return {
    apiBaseUrl: source.VITE_API_BASE_URL!.trim(),
    wsUrl: source.VITE_WS_URL!.trim(),
    appName: source.VITE_APP_NAME!.trim(),
    featureFlags: new Set(flags),
  }
}

export function readViteEnv(): AppEnv {
  return readAppEnv(import.meta.env)
}
