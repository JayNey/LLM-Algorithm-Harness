import { ApiClientError } from '../auth/http.ts'
import type {
  ABTestDraft,
  CreatePayload,
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

export function validateABTestDraft(draft: ABTestDraft): DraftErrors {
  const errors: DraftErrors = {}
  if (draft.name.trim().length > 200) errors.name = '名称不超过 200 字'
  if (!draft.dataset_path.trim()) errors.dataset_path = '请填写数据集路径'
  if (!draft.api_key_id.trim()) errors.api_key_id = '请选择可用密钥'
  if (!draft.model.trim()) errors.model = '请填写模型名'
  if (
    draft.model_temperature.trim() &&
    !validRange(draft.model_temperature, 0, 2)
  )
    errors.model = '模型温度须在 0–2 之间'
  if (!draft.strategy.trim()) errors.strategy = '请填写策略名'
  if (
    draft.strategy_max_iterations.trim() &&
    !validInteger(draft.strategy_max_iterations, 1, 10)
  )
    errors.strategy = '策略迭代须为 1–10 整数'
  if (
    draft.seed.trim() &&
    !validInteger(draft.seed, 0, Number.MAX_SAFE_INTEGER)
  )
    errors.seed = 'seed 须为非负整数'
  if (!validInteger(draft.max_workers, 1, 20))
    errors.max_workers = '并行数须为 1–20 的整数'
  const variants = draft.variants
  if (variants.length !== 2) errors.variants = '需要恰好两个 prompt 变体'
  else {
    const ids = variants.map((variant) => variant.id.trim())
    if (ids.some((id) => !id)) errors.variants = '每个变体都必须填写 ID'
    else if (ids[0] === ids[1]) errors.variants = '两个变体 ID 不得相同'
  }
  return errors
}

export function createPayload(draft: ABTestDraft): CreatePayload {
  const errors = validateABTestDraft(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('AB 测试配置无效', undefined, errors)
  return {
    name: draft.name.trim(),
    dataset_path: draft.dataset_path.trim(),
    model: {
      model: draft.model.trim(),
      ...(draft.model_temperature.trim()
        ? { temperature: Number(draft.model_temperature) }
        : {}),
    },
    strategy: {
      name: draft.strategy.trim(),
      ...(draft.strategy_max_iterations.trim()
        ? { max_iterations: Number(draft.strategy_max_iterations) }
        : {}),
    },
    prompt_variants: draft.variants.map((variant) => ({
      id: variant.id.trim(),
      ...(variant.description.trim()
        ? { description: variant.description.trim() }
        : {}),
      ...(variant.system_prompt.trim()
        ? { system_prompt: variant.system_prompt }
        : {}),
      ...(variant.prefix.trim() ? { prefix: variant.prefix } : {}),
      ...(variant.suffix.trim() ? { suffix: variant.suffix } : {}),
    })),
    seed: draft.seed.trim() ? Number(draft.seed) : 42,
    max_workers: Number(draft.max_workers),
    api_key_id: draft.api_key_id.trim(),
  }
}

function validRange(value: string, min: number, max: number): boolean {
  const number = Number(value)
  return Number.isFinite(number) && number >= min && number <= max
}

function validInteger(value: string, min: number, max: number): boolean {
  if (!/^\d+$/.test(value.trim())) return false
  const number = Number(value)
  return Number.isSafeInteger(number) && number >= min && number <= max
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
