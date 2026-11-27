import { budgetDraft, parseCustomParams, problemFilters } from './advanced.ts'
import { datasetConflict, datasetPayload } from '../experiments/datasets.ts'
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
  if (!draft.dataset_id?.trim() && !trimmed(draft.dataset_path))
    errors.dataset_path = '请选择个人题库或填写服务器数据集路径'
  if (datasetConflict(draft))
    errors.dataset_path = '请选择一种数据源，不能同时提供个人题库和服务器路径'
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
  draft.strategies.forEach((strategy, index) => {
    if (!strategy.name.trim()) return
    if (
      strategy.max_tokens?.trim() &&
      !validInteger(strategy.max_tokens, 100, 8000)
    )
      errors[`strategies.${index}.max_tokens`] =
        '最大生成 Token 须为 100–8000 的整数'
    try {
      parseCustomParams(strategy.name.trim(), strategy.custom_params)
    } catch (error) {
      errors[`strategies.${index}.custom_params`] = (error as Error).message
    }
  })
  const filters = draft.problem_filters
  if (
    filters?.limit?.trim() &&
    !validInteger(filters.limit, 1, Number.MAX_SAFE_INTEGER)
  )
    errors['problem_filters.limit'] = '题目数量上限须为正整数'
  if (
    filters?.difficulty &&
    !['easy', 'medium', 'hard'].includes(filters.difficulty)
  )
    errors['problem_filters.difficulty'] = '请选择有效难度'
  for (const [kind, value] of Object.entries(budgetDraft(draft))) {
    if (!value.trim() && draft.budget !== undefined) continue
    const error =
      kind === 'max_seconds'
        ? !validPositive(value.trim())
          ? '预算须为正数'
          : undefined
        : !validInteger(value, 1, Number.MAX_SAFE_INTEGER)
          ? '预算须为正整数'
          : undefined
    if (error) {
      errors[`budget.${kind}`] = error
      if (!draft.budget) errors.budget_value = error
    }
  }
  return errors
}

export function createExperimentPayload(draft: ExperimentDraft): CreatePayload {
  const errors = validateExperimentDraft(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('实验配置无效', undefined, errors)
  const values = Object.entries(budgetDraft(draft)).filter(([, value]) =>
    value.trim(),
  )
  const budget = values.length
    ? Object.fromEntries(values.map(([key, value]) => [key, Number(value)]))
    : null
  const filters = problemFilters(draft)
  return {
    name: trimmed(draft.name),
    ...datasetPayload(draft),
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
        ...(strategy.max_tokens?.trim()
          ? { max_tokens: Number(strategy.max_tokens) }
          : {}),
        ...(strategy.system_prompt?.trim()
          ? { system_prompt: strategy.system_prompt }
          : {}),
        ...(parseCustomParams(strategy.name.trim(), strategy.custom_params)
          ? {
              custom_params: parseCustomParams(
                strategy.name.trim(),
                strategy.custom_params,
              ),
            }
          : {}),
      })),
    repeats: Number(trimmed(draft.repeats)),
    budget,
    ...(filters ? { problem_filters: filters } : {}),
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
