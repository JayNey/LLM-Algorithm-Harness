import { parseCustomParams, problemFilters } from '../experiments/advanced.ts'
import { datasetConflict, datasetPayload } from '../experiments/datasets.ts'
import { ApiClientError } from '../auth/http.ts'
import type {
  BenchmarkRunRequestPayload,
  RunDraft,
  RunDraftErrors,
  SuiteCreateInput,
  SuiteDraft,
  SuiteDraftErrors,
} from './types.ts'

function lines(text: string): string[] {
  return [
    ...new Set(
      text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    ),
  ]
}

export function validateSuiteDraft(draft: SuiteDraft): SuiteDraftErrors {
  const errors: SuiteDraftErrors = {}
  const name = draft.name.trim()
  if (!name || name.length > 200) errors.name = '名称必填且不超过 200 字'
  if (draft.version.trim().length > 32) errors.version = '版本不超过 32 字'
  if (!lines(draft.problems_text).length)
    errors.problems_text = '至少填写一个题目 ID（每行一个）'
  return errors
}

export function suiteCreateInput(draft: SuiteDraft): SuiteCreateInput {
  const errors = validateSuiteDraft(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('基准套件配置无效', undefined, errors)
  return {
    name: draft.name.trim(),
    problems: lines(draft.problems_text),
    ...(draft.version.trim() ? { version: draft.version.trim() } : {}),
    ...(draft.description.trim()
      ? { description: draft.description.trim() }
      : {}),
    frozen: draft.frozen,
  }
}

export function runStrategies(draft: RunDraft) {
  return lines(draft.strategies_text.replace(/[,，]/g, '\n')).map((name) => ({
    name,
    max_iterations: '',
    temperature: '',
    ...draft.strategy_settings?.[name],
  }))
}

export function validateRunDraft(draft: RunDraft): RunDraftErrors {
  const errors: RunDraftErrors = {}
  if (!draft.api_key_id.trim()) errors.api_key_id = '请选择可用密钥'
  if (!draft.dataset_id?.trim() && !draft.dataset_path.trim())
    errors.dataset_path = '请选择个人题库或填写服务器数据集路径'
  if (datasetConflict(draft))
    errors.dataset_path = '请选择一种数据源，不能同时提供个人题库和服务器路径'
  if (!draft.model.trim()) errors.model = '请填写模型名'
  const budget = draft.budget_cap_usd.trim()
  if (budget && (!Number.isFinite(Number(budget)) || Number(budget) <= 0))
    errors.budget_cap_usd = '预算上限须为正数'
  runStrategies(draft).forEach((strategy, index) => {
    for (const [field, min, max] of [
      ['max_iterations', 1, 10],
      ['max_tokens', 100, 8000],
      ['temperature', 0, 2],
    ] as const) {
      const value = strategy[field]?.trim()
      if (
        value &&
        (!Number.isFinite(Number(value)) ||
          Number(value) < min ||
          Number(value) > max ||
          (field !== 'temperature' && !/^\d+$/.test(value)))
      )
        errors[`strategies.${index}.${field}`] =
          field === 'temperature'
            ? '策略温度须在 0–2 之间'
            : field === 'max_tokens'
              ? '最大生成 Token 须为 100–8000 的整数'
              : '策略迭代须为 1–10 整数'
    }
    try {
      parseCustomParams(strategy.name, strategy.custom_params)
    } catch (error) {
      errors[`strategies.${index}.custom_params`] = (error as Error).message
    }
  })
  const filters = draft.problem_filters
  if (
    filters?.limit?.trim() &&
    (!/^\d+$/.test(filters.limit.trim()) ||
      !Number.isSafeInteger(Number(filters.limit)) ||
      Number(filters.limit) < 1)
  )
    errors['problem_filters.limit'] = '题目数量上限须为正整数'
  if (
    filters?.difficulty?.trim() &&
    !['easy', 'medium', 'hard'].includes(filters.difficulty.trim())
  )
    errors['problem_filters.difficulty'] = '请选择有效难度'
  return errors
}

export function runPayload(draft: RunDraft): BenchmarkRunRequestPayload {
  const errors = validateRunDraft(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('基准运行配置无效', undefined, errors)
  const strategies = runStrategies(draft).map((strategy) => {
    const custom = parseCustomParams(strategy.name, strategy.custom_params)
    return {
      name: strategy.name,
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
      ...(custom ? { custom_params: custom } : {}),
    }
  })
  const filters = problemFilters(draft)
  return {
    api_key_id: draft.api_key_id.trim(),
    ...datasetPayload(draft),
    model: draft.model.trim(),
    ...(strategies.length ? { strategies } : {}),
    ...(filters ? { problem_filters: filters } : {}),
    ...(draft.budget_cap_usd.trim()
      ? { budget_cap_usd: Number(draft.budget_cap_usd) }
      : {}),
  }
}

export function suiteToDraft(suite: {
  name: string
  version: string
  description: string | null
  frozen: boolean
  problems: string[]
}): SuiteDraft {
  return {
    name: suite.name,
    version: suite.version,
    description: suite.description ?? '',
    frozen: suite.frozen,
    problems_text: suite.problems.join('\n'),
  }
}
