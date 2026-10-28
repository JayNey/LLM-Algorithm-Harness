import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  CatalogEntry,
  PricingCatalog,
  PricingClient,
  PricingVersion,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('定价接口响应格式不兼容', undefined, { field })
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
function positiveFloat(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0)
    protocol(field)
  return value
}

const SOURCES = ['builtin', 'custom_file', 'override']

function catalog(value: unknown): PricingCatalog {
  const data = record(value, 'pricing')
  const models = record(data.models, 'pricing.models')
  return {
    models: Object.fromEntries(
      Object.entries(models).map(([model, entry]) => {
        const row = record(entry, `pricing.models.${model}`)
        const source = row.source
        if (typeof source !== 'string' || !SOURCES.includes(source))
          protocol(`pricing.models.${model}.source`)
        return [
          model,
          {
            prompt_per_1k: positiveFloat(
              row.prompt_per_1k,
              `…${model}.prompt_per_1k`,
            ),
            completion_per_1k: positiveFloat(
              row.completion_per_1k,
              `…${model}.completion_per_1k`,
            ),
            source: source as CatalogEntry['source'],
          },
        ]
      }),
    ),
  }
}

function history(value: unknown): PricingVersion[] {
  if (!Array.isArray(value)) protocol('history')
  return value.map((item, index) => {
    const row = record(item, `history.${index}`)
    return {
      prompt_per_1k: positiveFloat(
        row.prompt_per_1k,
        `history.${index}.prompt_per_1k`,
      ),
      completion_per_1k: positiveFloat(
        row.completion_per_1k,
        `history.${index}.completion_per_1k`,
      ),
      created_by: text(row.created_by, `history.${index}.created_by`),
      created_at: text(row.created_at, `history.${index}.created_at`),
    }
  })
}

export function validateOverrideInput(input: {
  modelId: string
  prompt_per_1k: string
  completion_per_1k: string
}): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!input.modelId.trim()) errors.modelId = '请填写模型 ID'
  const positive = (value: string) =>
    Number.isFinite(Number(value)) && Number(value) > 0
  if (!positive(input.prompt_per_1k)) errors.prompt_per_1k = '须为正数'
  if (!positive(input.completion_per_1k)) errors.completion_per_1k = '须为正数'
  return errors
}

function modelPath(modelId: string): string {
  // Encode the complete ID once, including literal '%' and '/'. The API decodes once.
  return `/pricing/${encodeURIComponent(modelId)}`
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createPricingClient(http: AxiosInstance): PricingClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    signal?: AbortSignal,
  ): Promise<T> {
    return read(
      await http.get<unknown, unknown>(url, { signal, timeout: 10_000 }),
    )
  }
  return {
    catalog: async (signal) => get('/pricing', catalog, signal),
    history: async (modelId, signal) =>
      get(`${modelPath(modelId)}/history`, history, signal),
    addOverride: async (input) => {
      const errors = validateOverrideInput({
        modelId: input.modelId,
        prompt_per_1k: String(input.prompt_per_1k),
        completion_per_1k: String(input.completion_per_1k),
      })
      if (Object.keys(errors).length)
        throw new ApiClientError('定价配置无效', undefined, errors)
      const data = await http.post<unknown, unknown>(
        modelPath(input.modelId),
        {
          prompt_per_1k: input.prompt_per_1k,
          completion_per_1k: input.completion_per_1k,
        },
        { timeout: 20_000 },
      )
      const row = record(data, 'override')
      return {
        model: text(row.model, 'override.model'),
        prompt_per_1k: positiveFloat(
          row.prompt_per_1k,
          'override.prompt_per_1k',
        ),
        completion_per_1k: positiveFloat(
          row.completion_per_1k,
          'override.completion_per_1k',
        ),
      }
    },
  }
}
