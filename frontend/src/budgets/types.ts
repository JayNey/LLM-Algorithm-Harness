/** 预算与预警前端类型（issue #167 簇 B）。
 * 字段与 api/routes/costs.py + api/services/cost_service.py 的
 * _budget_view/_rule_view/budget_usage 真实形状对齐（owner 域端点）。
 */

export interface BudgetConfig {
  global_cap_usd: number | null
  difficulty_caps: Record<'easy' | 'medium' | 'hard', number | null>
  action: 'pause' | 'downgrade' | null
}

export interface BudgetUsageSection {
  cap_usd: number | null
  used_usd: number
  remaining_usd: number | null
  percentage_used: number | null
}

export interface BudgetUsage {
  global_budget: BudgetUsageSection
  by_difficulty: Record<
    'easy' | 'medium' | 'hard',
    {
      cap_usd: number | null
      used_usd: number
      percentage_used: number | null
    }
  >
}

export interface AlertRule {
  id: string
  name: string
  threshold_pct: number
  channel: string
  target: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type AlertChannel = 'slack' | 'webhook' | 'smtp' | 'log'

export interface BudgetClient {
  getBudget(signal?: AbortSignal): Promise<Partial<BudgetConfig>>
  saveBudget(config: Partial<BudgetConfig>): Promise<Partial<BudgetConfig>>
  usage(signal?: AbortSignal): Promise<BudgetUsage>
  alertRules(signal?: AbortSignal): Promise<AlertRule[]>
  createAlertRule(input: {
    name: string
    threshold_pct: number
    channel: AlertChannel
    target: string
    enabled: boolean
  }): Promise<AlertRule>
  updateAlertRule(
    ruleId: string,
    patch: {
      name?: string
      threshold_pct?: number
      channel?: AlertChannel
      target?: string
      enabled?: boolean
    },
  ): Promise<AlertRule>
  deleteAlertRule(ruleId: string): Promise<void>
}
