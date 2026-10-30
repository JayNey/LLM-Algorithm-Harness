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
  known_cost_usd?: number
  cost_complete?: boolean
  unknown_cost_count?: number
  unknown_reasons?: Record<string, number>
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

export interface CostCompleteness {
  known_cost_usd?: number
  cost_complete: boolean
  unknown_cost_count: number
  unknown_reasons: Record<string, number>
}

export interface CostSummary extends CostCompleteness {
  since: string | null
  until: string | null
  total_cost_usd: number
  task_count: number
  by_source: Record<string, number>
}

export interface CostTrendPoint {
  date: string
  cost_usd: number
  known_cost_usd: number
  cost_complete: boolean
  unknown_cost_count: number
  unknown_reasons: Record<string, number>
}

export interface CostTrends extends CostCompleteness {
  since: string | null
  until: string | null
  data: CostTrendPoint[]
}

export interface CostBreakdown extends CostCompleteness {
  since: string | null
  until: string | null
  by_source: Record<string, number>
  by_model: Record<string, number>
  by_strategy: Record<string, number>
}

export interface AlertEventRecord {
  id: string
  rule_id: string
  threshold_pct: number
  used_usd: number
  cap_usd: number
  channel: string
  triggered_at: string
}

export interface CostRange {
  since: string | null
  until: string | null
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
  costSummary(range: CostRange, signal?: AbortSignal): Promise<CostSummary>
  costTrends(range: CostRange, signal?: AbortSignal): Promise<CostTrends>
  costBreakdown(range: CostRange, signal?: AbortSignal): Promise<CostBreakdown>
  alertHistory(
    signal?: AbortSignal,
    limit?: number,
  ): Promise<AlertEventRecord[]>
}
