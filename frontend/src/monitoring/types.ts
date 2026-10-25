/** 系统监控前端类型（issue #167 簇 A）。
 * 字段与 api/routes/monitoring.py + api/monitoring/{service,probes,store,queue_probe}.py
 * 的真实响应形状对齐（admin 只读端点）。降级形态（unknown/窗口不完整/
 * not_configured）全部建模为可空。
 */

export interface HealthCheck {
  status: string
  detail?: string
}

export interface QueueWaiting {
  name: string
  waiting: number | null
}

export interface BrokerQueue {
  status: string
  waiting: number | null
  queues: QueueWaiting[] | null
}

export interface SystemHealth {
  status: string
  checks: {
    database: HealthCheck & { components?: Record<string, HealthCheck> }
    redis: HealthCheck & { broker_queue?: BrokerQueue }
    workers: HealthCheck & {
      worker_count?: number | null
      active?: number | null
      reserved?: number | null
      concurrency?: number | null
    }
    sandbox: HealthCheck
  }
}

export interface ResourceMeasure {
  cpu: { status: string; percent: number | null; sample_seconds: number }
  memory: {
    status: string
    total_bytes: number | null
    available_bytes: number | null
    used_bytes: number | null
    percent: number | null
  }
  disk: {
    status: string
    total_bytes: number | null
    used_bytes: number | null
    free_bytes: number | null
    percent: number | null
  }
}

export interface QueueMetrics {
  broker_queue: BrokerQueue
  database_pending: { status: string; count: number | null }
  worker_reserved: { status: string; count: number | null }
}

export interface SystemStatus {
  uptime_seconds: number
  /** 业务库不可用时为 null（降级形态） */
  task_count: number | null
  async_task_count: number | null
  task_counts: Record<string, number> | null
  async_task_counts: Record<string, number> | null
  health: SystemHealth
  resources: ResourceMeasure
  workers: SystemHealth['checks']['workers']
  queue_metrics: QueueMetrics
}

export interface ApiStats {
  request_count: number | null
  errors: number | null
  error_rate: number | null
  avg_response_time_ms: number | null
  p95_response_time_ms: number | null
  requests_per_second: number | null
  window_seconds: number
  window_complete: boolean
}

/** 窗口不完整时五字段为 null，保留 retained_sample 供回退展示。 */
export interface LlmStatsSample {
  total_calls: number | null
  successful_calls: number | null
  failed_calls: number | null
  success_rate: number | null
  avg_latency_ms: number | null
}

export interface LlmStats extends LlmStatsSample {
  window_complete?: boolean
  retained_sample?: LlmStatsSample
}

/** not_configured/共享观测形态下数值字段可空，仅 status 必有。 */
export interface CacheStats {
  status: string
  scope?: string
  enabled: boolean | null
  total_entries: number | null
  disk_usage_mb: number | null
  hit_rate: number | null
  hits: number | null
  misses: number | null
  api_calls_saved: number | null
}

export interface SandboxConfigView {
  backend: string
  docker_image: string
  timeout_seconds: number
  memory_limit_mb: number
  max_output_bytes: number
  max_processes: number
  allowed_imports: string[]
}

export interface StrategyInfo {
  name: string
  defaults: Record<string, unknown>
}

/** providers 端点：status + 数组 [{provider, models}]。 */
export interface ProvidersCatalog {
  status: string
  live_provider_availability_checked: boolean
  providers: { provider: string; models: string[] }[]
}

export interface MonitoringClient {
  systemStatus(signal?: AbortSignal): Promise<SystemStatus>
  apiStats(windowSeconds: number, signal?: AbortSignal): Promise<ApiStats>
  llmStats(
    windowSeconds: number | null,
    signal?: AbortSignal,
  ): Promise<LlmStats>
  cacheStats(signal?: AbortSignal): Promise<CacheStats>
  sandboxConfig(signal?: AbortSignal): Promise<SandboxConfigView>
  strategies(signal?: AbortSignal): Promise<StrategyInfo[]>
  providers(signal?: AbortSignal): Promise<ProvidersCatalog>
}
