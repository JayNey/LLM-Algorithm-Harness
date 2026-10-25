import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  AlertChannel,
  AlertRule,
  BudgetClient,
  BudgetConfig,
  BudgetUsage,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('预算接口响应格式不兼容', undefined, { field })
}
function record(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    protocol(field)
  return value as Record<string, unknown>
}
function text(value: unknown, field: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && !value.trim()))
    protocol(field)
  return value
}
function count(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
    protocol(field)
  return value
}
function nullableFloat(value: unknown, field: string): number | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0)
    protocol(field)
  return value
}
function boolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') protocol(field)
  return value
}
function difficultyCaps(
  value: unknown,
  field: string,
): BudgetConfig['difficulty_caps'] {
  const data = record(value, field)
  const read = (key: string) =>
    data[key] === undefined || data[key] === null
      ? null
      : nullableFloat(data[key], `${field}.${key}`)
  return { easy: read('easy'), medium: read('medium'), hard: read('hard') }
}

const DIFFICULTIES = ['easy', 'medium', 'hard'] as const

function budgetConfig(value: unknown): Partial<BudgetConfig> {
  // get_budget 无配置时返回 {}（空对象合法）
  const keys = Object.keys(value as object)
  if (keys.length === 0) return {}
  const data = record(value, 'budget')
  const action = data.action
  if (
    action !== null &&
    action !== undefined &&
    action !== 'pause' &&
    action !== 'downgrade'
  )
    protocol('budget.action')
  return {
    global_cap_usd: nullableFloat(data.global_cap_usd, 'budget.global_cap_usd'),
    difficulty_caps: difficultyCaps(
      data.difficulty_caps,
      'budget.difficulty_caps',
    ),
    action: (action as BudgetConfig['action']) ?? null,
  }
}

function usageSection(
  value: unknown,
  field: string,
): BudgetUsage['global_budget'] {
  const data = record(value, field)
  return {
    cap_usd: nullableFloat(data.cap_usd, `${field}.cap_usd`),
    used_usd: nullableFloat(data.used_usd, `${field}.used_usd`) ?? 0,
    remaining_usd: nullableFloat(data.remaining_usd, `${field}.remaining_usd`),
    percentage_used: nullableFloat(
      data.percentage_used,
      `${field}.percentage_used`,
    ),
  }
}

function budgetUsage(value: unknown): BudgetUsage {
  const data = record(value, 'usage')
  const byDifficulty = record(data.by_difficulty, 'usage.by_difficulty')
  return {
    global_budget: usageSection(data.global_budget, 'usage.global_budget'),
    by_difficulty: Object.fromEntries(
      DIFFICULTIES.map((key) => {
        const section = record(byDifficulty[key], `usage.by_difficulty.${key}`)
        return [
          key,
          {
            cap_usd: nullableFloat(section.cap_usd, `…${key}.cap_usd`),
            used_usd: nullableFloat(section.used_usd, `…${key}.used_usd`) ?? 0,
            percentage_used: nullableFloat(
              section.percentage_used,
              `…${key}.percentage_used`,
            ),
          },
        ]
      }),
    ) as BudgetUsage['by_difficulty'],
  }
}

function alertRule(value: unknown, field: string): AlertRule {
  const data = record(value, field)
  return {
    id: text(data.id, `${field}.id`),
    name: text(data.name, `${field}.name`, true),
    threshold_pct: count(data.threshold_pct, `${field}.threshold_pct`),
    channel: text(data.channel, `${field}.channel`),
    target: text(data.target, `${field}.target`, true),
    enabled: boolean(data.enabled, `${field}.enabled`),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
  }
}

const CHANNELS: AlertChannel[] = ['slack', 'webhook', 'smtp', 'log']

export function validateAlertInput(input: {
  threshold_pct: number
  channel: AlertChannel
  target: string
}): string | null {
  if (
    !Number.isInteger(input.threshold_pct) ||
    input.threshold_pct < 1 ||
    input.threshold_pct > 100
  )
    return '阈值须为 1–100 的整数百分比'
  if (!CHANNELS.includes(input.channel)) return '渠道不支持'
  if (input.channel !== 'log' && !input.target.trim())
    return `渠道 ${input.channel} 需要填写通知目标`
  return null
}

export function validateBudgetInput(input: {
  global_cap_usd: string
  easy: string
  medium: string
  hard: string
}): Record<string, string> {
  const errors: Record<string, string> = {}
  const positive = (value: string) =>
    value.trim() === '' || (Number.isFinite(Number(value)) && Number(value) > 0)
  if (!positive(input.global_cap_usd))
    errors.global_cap_usd = '全局上限须为正数'
  if (!positive(input.easy)) errors.easy = '须为正数'
  if (!positive(input.medium)) errors.medium = '须为正数'
  if (!positive(input.hard)) errors.hard = '须为正数'
  return errors
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createBudgetClient(http: AxiosInstance): BudgetClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    signal?: AbortSignal,
  ): Promise<T> {
    return read(
      await http.get<unknown, unknown>(url, { signal, timeout: 10_000 }),
    )
  }
  async function mutate<T>(
    url: string,
    method: 'post' | 'patch',
    body: unknown,
    read: (value: unknown) => T,
  ): Promise<T> {
    const request =
      method === 'post'
        ? http.post<unknown, unknown>(url, body, { timeout: 20_000 })
        : http.patch<unknown, unknown>(url, body, { timeout: 20_000 })
    return read(await request)
  }
  return {
    getBudget: async (signal) => get('/budgets', budgetConfig, signal),
    saveBudget: async (config) => {
      const body: Record<string, unknown> = {}
      if (config.global_cap_usd !== undefined)
        body.global_cap_usd = config.global_cap_usd
      if (config.difficulty_caps !== undefined) {
        const caps: Record<string, number> = {}
        for (const key of DIFFICULTIES) {
          const cap = config.difficulty_caps[key]
          if (cap !== null) caps[key] = cap
        }
        body.difficulty_caps = caps
      }
      if (config.action !== undefined && config.action !== null)
        body.action = config.action
      return mutate('/budgets', 'patch', body, budgetConfig)
    },
    usage: async (signal) => get('/budgets/usage', budgetUsage, signal),
    alertRules: async (signal) => {
      const data = await http.get<unknown, unknown>('/alerts', {
        signal,
        timeout: 10_000,
      })
      const rows = data as unknown[]
      if (!Array.isArray(rows)) protocol('alerts')
      return rows.map((row, index) => alertRule(row, `alerts.${index}`))
    },
    createAlertRule: async (input) => {
      const error = validateAlertInput(input)
      if (error) throw new ApiClientError(error)
      return mutate('/alerts', 'post', input, (value) =>
        alertRule(value, 'alert'),
      )
    },
    updateAlertRule: async (ruleId, patch) => {
      if (patch.threshold_pct !== undefined || patch.channel !== undefined) {
        const error = validateAlertInput({
          threshold_pct: patch.threshold_pct ?? 50,
          channel: patch.channel ?? 'log',
          target: patch.target ?? '',
        })
        if (error) throw new ApiClientError(error)
      }
      return mutate(
        `/alerts/${encodeURIComponent(ruleId)}`,
        'patch',
        patch,
        (value) => alertRule(value, 'alert'),
      )
    },
    deleteAlertRule: async (ruleId) => {
      await http.delete(`/alerts/${encodeURIComponent(ruleId)}`, {
        timeout: 20_000,
      })
    },
  }
}
