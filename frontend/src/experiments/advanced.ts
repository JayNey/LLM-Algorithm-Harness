import { t } from '../i18n/core.ts'
import type { ExperimentDraft, ProblemFilters, ProblemBudget } from './types.ts'

type Rule = { min?: number; max?: number; integer?: boolean; values?: string[] }
// Only existing in-process strategy controls; no file paths or connection options.
export const strategyControls: Record<string, Record<string, Rule>> = {
  self_consistency: {
    num_candidates: { min: 1, integer: true },
    temperature: { min: 0, max: 2 },
  },
  tree_of_thoughts: {
    branching_factor: { min: 1, integer: true },
    max_depth: { min: 1, integer: true },
    search_strategy: { values: ['bfs', 'dfs'] },
    pruning_threshold: { min: 0, max: 1 },
  },
  few_shot_learning: {
    num_examples: { min: 0, integer: true },
    similarity_metric: { values: ['tag_overlap'] },
    min_similarity_score: { min: 0, max: 1 },
  },
  reflexion: { reflection_context_chars: { min: 1, integer: true } },
}

export function parseCustomParams(
  name: string,
  input = '',
): Record<string, unknown> | undefined {
  if (!input.trim()) return undefined
  let value: unknown
  try {
    value = JSON.parse(input)
  } catch {
    throw new Error(t('自定义参数须为有效 JSON 对象'))
  }
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error(t('自定义参数须为有效 JSON 对象'))
  const rules = strategyControls[name] ?? {}
  for (const [key, item] of Object.entries(value)) {
    const rule = Object.hasOwn(rules, key) ? rules[key] : undefined
    if (!rule) throw new Error(t('不支持的策略参数：{{key}}', { key }))
    const valid = rule.values
      ? typeof item === 'string' && rule.values.includes(item)
      : typeof item === 'number' &&
        Number.isFinite(item) &&
        (!rule.integer || Number.isSafeInteger(item)) &&
        (rule.min === undefined || item >= rule.min) &&
        (rule.max === undefined || item <= rule.max)
    if (!valid)
      throw new Error(
        t('策略参数 {{key}} 无效；要求 {{rule}}', {
          key,
          rule:
            rule.values?.join(' / ') ??
            `${rule.integer ? t('整数') : t('数值')} ≥ ${rule.min}${rule.max === undefined ? '' : ` ≤ ${rule.max}`}`,
        }),
      )
  }
  return Object.keys(value).length
    ? (value as Record<string, unknown>)
    : undefined
}

export function splitFilterList(input = ''): string[] {
  return [
    ...new Set(
      input
        .split(/[,，\r\n]+/)
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  ]
}

export function problemFilters(
  draft: Pick<ExperimentDraft, 'problem_filters'>,
): ProblemFilters | undefined {
  const raw = draft.problem_filters ?? {}
  const tags = splitFilterList(raw.tags)
  const ids = splitFilterList(raw.problem_ids)
  const value = {
    ...(raw.difficulty?.trim() ? { difficulty: raw.difficulty.trim() } : {}),
    ...(tags.length ? { tags } : {}),
    ...(ids.length ? { problem_ids: ids } : {}),
    ...(raw.limit?.trim() ? { limit: Number(raw.limit) } : {}),
  }
  return Object.keys(value).length ? value : undefined
}

export function budgetDraft(
  draft: ExperimentDraft,
): Partial<Record<keyof ProblemBudget, string>> {
  return (
    draft.budget ??
    (draft.budget_kind === 'none'
      ? {}
      : { [draft.budget_kind]: draft.budget_value })
  )
}

export function filterSummary(filters?: ProblemFilters | null): string {
  const parts = [
    filters?.difficulty
      ? t('难度：{{value}}', { value: filters.difficulty })
      : '',
    filters?.tags?.length
      ? t('标签（任一）：{{value}}', { value: filters.tags.join(', ') })
      : '',
    filters?.problem_ids?.length
      ? t('题目 ID：{{value}}', { value: filters.problem_ids.join(', ') })
      : '',
    filters?.limit !== undefined
      ? t('最后取前 {{value}} 题', { value: filters.limit })
      : '',
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : t('全部题目（未筛选）')
}
