/** 定价管理前端类型（issue #167 簇 C）。
 * 字段与 api/services/cost_service.py 的 pricing_catalog/pricing_history/
 * set_pricing_override 真实形状对齐（owner 域端点）。
 */

export type PricingSource = 'builtin' | 'custom_file' | 'override'

export interface CatalogEntry {
  prompt_per_1k: number
  completion_per_1k: number
  source: PricingSource
}

export interface PricingCatalog {
  models: Record<string, CatalogEntry>
}

export interface PricingVersion {
  prompt_per_1k: number
  completion_per_1k: number
  created_by: string
  created_at: string
}

export interface PricingClient {
  catalog(signal?: AbortSignal): Promise<PricingCatalog>
  history(modelId: string, signal?: AbortSignal): Promise<PricingVersion[]>
  addOverride(input: {
    modelId: string
    prompt_per_1k: number
    completion_per_1k: number
  }): Promise<{
    model: string
    prompt_per_1k: number
    completion_per_1k: number
  }>
}
