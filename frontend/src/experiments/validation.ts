import { ApiClientError } from '../auth/http.ts'
import type {
  CreatePayload,
  DraftErrors,
  ExperimentDraft,
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

function trimmed(value: string): string {
  return value.trim()
}

export function validateExperimentDraft(draft: ExperimentDraft): DraftErrors {
  const errors: DraftErrors = {}
  if (!trimmed(draft.dataset_path))
    errors.dataset_path = '请填写数据集路径（DATA_ROOT 下的相对路径）'
  if (!trimmed(draft.api_key_id)) errors.api_key_id = '请选择可用密钥'
  const models = draft.models.filter((model) => trimmed(model.model))
  if (!models.length) errors.models = '至少配置一个模型'
  else if (
    models.some(
      (model) =>
        (model.temperature.trim() && !validRange(model.temperature, 0, 2)) ||
        models.filter((m) => trimmed(m.model) === trimmed(model.model)).length >
          1,
    )
  )
    errors.models = '模型温度须在 0–2 之间且不得重复'
  const strategies = draft.strategies.filter((strategy) =>
    trimmed(strategy.name),
  )
  if (!strategies.length) errors.strategies = '至少选择一个策略'
  else if (
    strategies.some(
      (strategy) =>
        (strategy.max_iterations.trim() &&
          !validInteger(strategy.max_iterations, 1, 10)) ||
        (strategy.temperature.trim() &&
          !validRange(strategy.temperature, 0, 2)),
    )
  )
    errors.strategies = '策略迭代须为 1–10 整数、温度须在 0–2 之间'
  if (!validInteger(draft.repeats, 1, 1000))
    errors.repeats = '重复次数须为正整数'
  if (!validInteger(draft.max_workers, 1, 16))
    errors.max_workers = '并行数须为 1–16 的整数'
  if (draft.budget_kind !== 'none') {
    const value = draft.budget_value.trim()
    if (!value || !validPositive(value)) errors.budget_value = '预算须为正数'
  }
  return errors
}

export function createExperimentPayload(draft: ExperimentDraft): CreatePayload {
  const errors = validateExperimentDraft(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('实验配置无效', undefined, errors)
  const budget =
    draft.budget_kind === 'none'
      ? null
      : {
          [draft.budget_kind]: Number(trimmed(draft.budget_value)),
        }
  return {
    name: trimmed(draft.name),
    dataset_path: trimmed(draft.dataset_path),
    models: draft.models
      .filter((model) => trimmed(model.model))
      .map((model) => ({
        model: trimmed(model.model),
        ...(model.temperature.trim()
          ? { temperature: Number(model.temperature) }
          : {}),
        ...(trimmed(model.api_key_id)
          ? { api_key_id: trimmed(model.api_key_id) }
          : {}),
      })),
    strategies: draft.strategies
      .filter((strategy) => trimmed(strategy.name))
      .map((strategy) => ({
        name: trimmed(strategy.name),
        ...(strategy.max_iterations.trim()
          ? { max_iterations: Number(strategy.max_iterations) }
          : {}),
        ...(strategy.temperature.trim()
          ? { temperature: Number(strategy.temperature) }
          : {}),
      })),
    repeats: Number(trimmed(draft.repeats)),
    budget,
    execution: draft.execution,
    max_workers: Number(trimmed(draft.max_workers)),
    api_key_id: trimmed(draft.api_key_id),
  }
}

function validRange(value: string, min: number, max: number): boolean {
  const number = Number(value)
  return Number.isFinite(number) && number >= min && number <= max
}

function validInteger(value: string, min: number, max: number): boolean {
  if (!/^\d+$/.test(trimmed(value))) return false
  const number = Number(trimmed(value))
  return Number.isSafeInteger(number) && number >= min && number <= max
}

function validPositive(value: string): boolean {
  const number = Number(value)
  return Number.isFinite(number) && number > 0
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
