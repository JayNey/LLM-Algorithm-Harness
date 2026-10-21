import { ApiClientError } from '../auth/http.ts'
import type {
  CreatePayload,
  Draft,
  DraftAvailable,
  DraftErrors,
  ListQuery,
} from './types.ts'

const statuses = new Set([
  'pending',
  'running',
  'paused',
  'completed',
  'failed',
  'cancelled',
])

function unique(values: readonly string[]): string[] {
  return [...new Set(values.map((value) => value.trim()))]
}

function draftErrors(draft: Draft, available?: DraftAvailable): DraftErrors {
  const errors: DraftErrors = {}
  const key = draft.api_key_id.trim()
  const model = draft.model.trim()
  if (!key || (available && !available.api_key_ids.includes(key)))
    errors.api_key_id = '请选择可用密钥'
  if (!model || (available && !available.models.includes(model)))
    errors.model = '请选择已加载的模型'
  const problems = unique(draft.problem_ids)
  if (
    !problems.length ||
    problems.some(
      (id) => !id || (available && !available.problem_ids.includes(id)),
    )
  )
    errors.problem_ids = '请选择当前来源的可用题目'
  const strategies = unique(draft.strategy_names)
  if (
    !strategies.length ||
    strategies.some(
      (name) =>
        !name || (available && !available.strategy_names.includes(name)),
    )
  )
    errors.strategy_names = '请选择可用策略'
  const budget = draft.budget_cap_usd.trim()
  if (budget && (!Number.isFinite(Number(budget)) || Number(budget) < 0))
    errors.budget_cap_usd = '预算必须为有限非负数'
  return errors
}

export function validateDraft(
  draft: Draft,
  available: DraftAvailable,
): DraftErrors {
  return draftErrors(draft, available)
}

export function createPayload(draft: Draft): CreatePayload {
  const errors = draftErrors(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('评估配置无效', undefined, errors)
  const payload: CreatePayload = {
    api_key_id: draft.api_key_id.trim(),
    model: draft.model.trim(),
    problem_ids: unique(draft.problem_ids),
    strategy_names: unique(draft.strategy_names),
  }
  if (draft.budget_cap_usd.trim())
    payload.budget_cap_usd = Number(draft.budget_cap_usd)
  return payload
}

function integer(
  value: string | null,
  fallback: number,
  min: number,
  max: number,
): number {
  if (!value || !/^\d+$/.test(value)) return fallback
  const number = Number(value)
  return Number.isSafeInteger(number) && number >= min && number <= max
    ? number
    : fallback
}

export function readListQuery(search: URLSearchParams): ListQuery {
  const status = search.get('status')
  return {
    ...(status && statuses.has(status) ? { status } : {}),
    limit: integer(search.get('limit'), 20, 1, 100),
    offset: integer(search.get('offset'), 0, 0, Number.MAX_SAFE_INTEGER),
  }
}

export function writeListQuery(query: ListQuery): URLSearchParams {
  const normalized = readListQuery(
    new URLSearchParams({
      status: query.status ?? '',
      limit: String(query.limit),
      offset: String(query.offset),
    }),
  )
  const search = new URLSearchParams()
  if (normalized.status) search.set('status', normalized.status)
  search.set('limit', String(normalized.limit))
  search.set('offset', String(normalized.offset))
  return search
}
