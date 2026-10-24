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

export function validateRunDraft(draft: RunDraft): RunDraftErrors {
  const errors: RunDraftErrors = {}
  if (!draft.api_key_id.trim()) errors.api_key_id = '请选择可用密钥'
  if (!draft.dataset_path.trim()) errors.dataset_path = '请填写数据集路径'
  if (!draft.model.trim()) errors.model = '请填写模型名'
  const budget = draft.budget_cap_usd.trim()
  if (budget && (!Number.isFinite(Number(budget)) || Number(budget) <= 0))
    errors.budget_cap_usd = '预算上限须为正数'
  return errors
}

export function runPayload(draft: RunDraft): BenchmarkRunRequestPayload {
  const errors = validateRunDraft(draft)
  if (Object.keys(errors).length)
    throw new ApiClientError('基准运行配置无效', undefined, errors)
  // 后端要求 StrategyConfig 对象数组，不是字符串数组
  const strategies = lines(draft.strategies_text.replace(/[,，]/g, '\n')).map(
    (name) => ({ name }),
  )
  return {
    api_key_id: draft.api_key_id.trim(),
    dataset_path: draft.dataset_path.trim(),
    model: draft.model.trim(),
    ...(strategies.length ? { strategies } : {}),
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
