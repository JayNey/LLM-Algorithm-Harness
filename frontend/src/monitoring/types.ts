/** 系统监控前端类型（issue #167 簇 A）。
 * 字段与 api/routes/monitoring.py + api/monitoring/{service,probes,store}.py
 * 的真实响应形状对齐；全部为 admin 只读端点。
 */

export interface HealthCheck {
  status: string
  detail?: string
}

export interface SystemHealth {
  status: string
  checks: {
    database: HealthCheck & { components?: Record<string, HealthCheck> }
    redis: HealthCheck & { waiting?: number | null; queues?: string[] | null }
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
  broker_queue: {
    status: string
    waiting: number | null
    queues: string[] | null
  }
  database_pending: { status: string; count: number | null }
  worker_reserved: { status: string; count: number | null }
}

export interface SystemStatus {
  uptime_seconds: number
  task_count: number
  async_task_count: number
  task_counts: Record<string, number>
  async_task_counts: Record<string, number>
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

export interface LlmStats {
  total_calls: number
  successful_calls: number
  failed_calls: number
  success_rate: number | null
  avg_latency_ms: number | null
}

export interface CacheStats {
  enabled: boolean
  total_entries: number
  disk_usage_mb: number
  hit_rate: number | null
  hits: number
  misses: number
  api_calls_saved: number
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

export interface ProvidersCatalog {
  available: boolean
  providers: Record<string, { models: string[]; source: string }>
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
