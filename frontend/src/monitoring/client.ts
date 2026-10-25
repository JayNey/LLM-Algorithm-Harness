import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  ApiStats,
  BrokerQueue,
  CacheStats,
  LlmStats,
  LlmStatsSample,
  MonitoringClient,
  ProvidersCatalog,
  QueueMetrics,
  ResourceMeasure,
  SandboxConfigView,
  StrategyInfo,
  SystemHealth,
  SystemStatus,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('监控接口响应格式不兼容', undefined, { field })
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
function nullableText(value: unknown, field: string): string | null {
  return value === null || value === undefined ? null : text(value, field, true)
}
function count(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
    protocol(field)
  return value
}
function nullableCount(value: unknown, field: string): number | null {
  return value === null || value === undefined ? null : count(value, field)
}
function nullableFloat(value: unknown, field: string): number | null {
  if (value === null || value === undefined) return null
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0)
    protocol(field)
  return value
}
function boolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') protocol(field)
  return value
}
function nullableBoolean(value: unknown, field: string): boolean | null {
  return value === null || value === undefined ? null : boolean(value, field)
}
function array(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) protocol(field)
  return value
}

function healthCheck(value: unknown, field: string) {
  const row = record(value, field)
  return {
    status: text(row.status, `${field}.status`, true),
    ...(row.detail !== undefined
      ? { detail: nullableText(row.detail, `${field}.detail`) ?? '' }
      : {}),
  }
}

function brokerQueue(value: unknown, field: string): BrokerQueue {
  const row = record(value, field)
  // queue_probe 真实形状：queues 为 [{name, waiting}]（未知时为 null）
  return {
    status: text(row.status, `${field}.status`, true),
    waiting: nullableCount(row.waiting, `${field}.waiting`),
    queues:
      row.queues === null || row.queues === undefined
        ? null
        : array(row.queues, `${field}.queues`).map((item, index) => {
            const entry = record(item, `${field}.queues.${index}`)
            return {
              name: text(entry.name, `${field}.queues.${index}.name`),
              waiting: nullableCount(
                entry.waiting,
                `${field}.queues.${index}.waiting`,
              ),
            }
          }),
  }
}

function workersCheck(value: unknown, field: string) {
  const row = record(value, field)
  return {
    ...healthCheck(row, field),
    worker_count: nullableCount(row.worker_count, `${field}.worker_count`),
    active: nullableCount(row.active, `${field}.active`),
    reserved: nullableCount(row.reserved, `${field}.reserved`),
    concurrency: nullableCount(row.concurrency, `${field}.concurrency`),
  }
}

function systemHealth(value: unknown): SystemHealth {
  const data = record(value, 'health')
  const checks = record(data.checks, 'health.checks')
  const database = record(checks.database, 'health.checks.database')
  const redis = record(checks.redis, 'health.checks.redis')
  const sandbox = record(checks.sandbox, 'health.checks.sandbox')
  const components =
    database.components === undefined || database.components === null
      ? undefined
      : Object.fromEntries(
          Object.entries(
            record(database.components, '…database.components'),
          ).map(([key, item]) => [
            key,
            healthCheck(item, `…database.components.${key}`),
          ]),
        )
  return {
    status: text(data.status, 'health.status', true),
    checks: {
      database: {
        ...healthCheck(database, 'health.checks.database'),
        components,
      },
      redis: {
        ...healthCheck(redis, 'health.checks.redis'),
        ...(redis.broker_queue !== undefined && redis.broker_queue !== null
          ? {
              broker_queue: brokerQueue(
                redis.broker_queue,
                'health.checks.redis.broker_queue',
              ),
            }
          : {}),
      },
      workers: workersCheck(checks.workers, 'health.checks.workers'),
      sandbox: healthCheck(sandbox, 'health.checks.sandbox'),
    },
  }
}

function resourceMeasure(value: unknown): ResourceMeasure {
  const data = record(value, 'resources')
  const cpu = record(data.cpu, 'resources.cpu')
  const memory = record(data.memory, 'resources.memory')
  const disk = record(data.disk, 'resources.disk')
  return {
    cpu: {
      status: text(cpu.status, 'resources.cpu.status', true),
      percent: nullableFloat(cpu.percent, 'resources.cpu.percent'),
      // probes.py 固定 0.1s 采样窗口——浮点
      sample_seconds:
        nullableFloat(cpu.sample_seconds, 'resources.cpu.sample_seconds') ?? 0,
    },
    memory: {
      status: text(memory.status, 'resources.memory.status', true),
      total_bytes: nullableCount(
        memory.total_bytes,
        'resources.memory.total_bytes',
      ),
      available_bytes: nullableCount(
        memory.available_bytes,
        'resources.memory.available_bytes',
      ),
      used_bytes: nullableCount(
        memory.used_bytes,
        'resources.memory.used_bytes',
      ),
      percent: nullableFloat(memory.percent, 'resources.memory.percent'),
    },
    disk: {
      status: text(disk.status, 'resources.disk.status', true),
      total_bytes: nullableCount(
        disk.total_bytes,
        'resources.disk.total_bytes',
      ),
      used_bytes: nullableCount(disk.used_bytes, 'resources.disk.used_bytes'),
      free_bytes: nullableCount(disk.free_bytes, 'resources.disk.free_bytes'),
      percent: nullableFloat(disk.percent, 'resources.disk.percent'),
    },
  }
}

function nullableCountsMap(
  value: unknown,
  field: string,
): Record<string, number> | null {
  if (value === null || value === undefined) return null
  return Object.fromEntries(
    Object.entries(record(value, field)).map(([key, item]) => [
      key,
      count(item, `${field}.${key}`),
    ]),
  )
}

function queueMetrics(value: unknown): QueueMetrics {
  const data = record(value, 'queue_metrics')
  const pending = record(
    data.database_pending,
    'queue_metrics.database_pending',
  )
  const reserved = record(data.worker_reserved, 'queue_metrics.worker_reserved')
  return {
    broker_queue: brokerQueue(data.broker_queue, 'queue_metrics.broker_queue'),
    database_pending: {
      status: text(
        pending.status,
        'queue_metrics.database_pending.status',
        true,
      ),
      count: nullableCount(
        pending.count,
        'queue_metrics.database_pending.count',
      ),
    },
    worker_reserved: {
      status: text(
        reserved.status,
        'queue_metrics.worker_reserved.status',
        true,
      ),
      count: nullableCount(
        reserved.count,
        'queue_metrics.worker_reserved.count',
      ),
    },
  }
}

function systemStatus(value: unknown): SystemStatus {
  const data = record(value, 'system-status')
  return {
    uptime_seconds:
      nullableFloat(data.uptime_seconds, 'system-status.uptime_seconds') ?? 0,
    // 业务库不可用时 read_task_snapshot 返回 total/counts = None
    task_count: nullableCount(data.task_count, 'system-status.task_count'),
    async_task_count: nullableCount(
      data.async_task_count,
      'system-status.async_task_count',
    ),
    task_counts: nullableCountsMap(
      data.task_counts,
      'system-status.task_counts',
    ),
    async_task_counts: nullableCountsMap(
      data.async_task_counts,
      'system-status.async_task_counts',
    ),
    health: systemHealth(data.health),
    resources: resourceMeasure(data.resources),
    workers: workersCheck(data.workers, 'system-status.workers'),
    queue_metrics: queueMetrics(data.queue_metrics),
  }
}

function apiStats(value: unknown): ApiStats {
  const data = record(value, 'api-stats')
  return {
    request_count: nullableCount(data.request_count, 'api-stats.request_count'),
    errors: nullableCount(data.errors, 'api-stats.errors'),
    error_rate: nullableFloat(data.error_rate, 'api-stats.error_rate'),
    avg_response_time_ms: nullableFloat(
      data.avg_response_time_ms,
      'api-stats.avg_response_time_ms',
    ),
    p95_response_time_ms: nullableFloat(
      data.p95_response_time_ms,
      'api-stats.p95_response_time_ms',
    ),
    requests_per_second: nullableFloat(
      data.requests_per_second,
      'api-stats.requests_per_second',
    ),
    window_seconds: count(data.window_seconds, 'api-stats.window_seconds'),
    window_complete: boolean(data.window_complete, 'api-stats.window_complete'),
  }
}

function llmSample(value: unknown, field: string): LlmStatsSample {
  const data = record(value, field)
  return {
    total_calls: nullableCount(data.total_calls, `${field}.total_calls`),
    successful_calls: nullableCount(
      data.successful_calls,
      `${field}.successful_calls`,
    ),
    failed_calls: nullableCount(data.failed_calls, `${field}.failed_calls`),
    success_rate: nullableFloat(data.success_rate, `${field}.success_rate`),
    avg_latency_ms: nullableFloat(
      data.avg_latency_ms,
      `${field}.avg_latency_ms`,
    ),
  }
}

function llmStats(value: unknown): LlmStats {
  const data = record(value, 'llm-stats')
  // 全量模式：五字段必有值；窗口模式：不完整时全 null + retained_sample
  const result = llmSample(value, 'llm-stats')
  return {
    ...result,
    ...(data.window_complete !== undefined
      ? {
          window_complete: boolean(
            data.window_complete,
            'llm-stats.window_complete',
          ),
        }
      : {}),
    ...(data.retained_sample !== undefined && data.retained_sample !== null
      ? {
          retained_sample: llmSample(
            data.retained_sample,
            'llm-stats.retained_sample',
          ),
        }
      : {}),
  }
}

function cacheStats(value: unknown): CacheStats {
  const data = record(value, 'cache-stats')
  // not_configured / 共享观测降级：仅 status（+scope），数值字段可空
  return {
    status: text(data.status, 'cache-stats.status', true),
    ...(data.scope !== undefined
      ? { scope: text(data.scope, 'cache-stats.scope', true) }
      : {}),
    enabled: nullableBoolean(data.enabled, 'cache-stats.enabled'),
    total_entries: nullableCount(
      data.total_entries,
      'cache-stats.total_entries',
    ),
    disk_usage_mb: nullableFloat(
      data.disk_usage_mb,
      'cache-stats.disk_usage_mb',
    ),
    hit_rate: nullableFloat(data.hit_rate, 'cache-stats.hit_rate'),
    hits: nullableCount(data.hits, 'cache-stats.hits'),
    misses: nullableCount(data.misses, 'cache-stats.misses'),
    api_calls_saved: nullableCount(
      data.api_calls_saved,
      'cache-stats.api_calls_saved',
    ),
  }
}

function sandboxConfig(value: unknown): SandboxConfigView {
  const data = record(value, 'sandbox-config')
  return {
    backend: text(data.backend, 'sandbox-config.backend'),
    docker_image: text(data.docker_image, 'sandbox-config.docker_image'),
    timeout_seconds: count(
      data.timeout_seconds,
      'sandbox-config.timeout_seconds',
    ),
    memory_limit_mb: count(
      data.memory_limit_mb,
      'sandbox-config.memory_limit_mb',
    ),
    max_output_bytes: count(
      data.max_output_bytes,
      'sandbox-config.max_output_bytes',
    ),
    max_processes: count(data.max_processes, 'sandbox-config.max_processes'),
    allowed_imports:
      data.allowed_imports === undefined || data.allowed_imports === null
        ? []
        : array(data.allowed_imports, 'sandbox-config.allowed_imports').map(
            (item, index) =>
              text(item, `sandbox-config.allowed_imports.${index}`),
          ),
  }
}

function strategies(value: unknown): StrategyInfo[] {
  const data = record(value, 'strategies-response')
  return array(data.strategies, 'strategies').map((item, index) => {
    const row = record(item, `strategies.${index}`)
    return {
      name: text(row.name, `strategies.${index}.name`),
      defaults: record(row.defaults, `strategies.${index}.defaults`),
    }
  })
}

function providers(value: unknown): ProvidersCatalog {
  const data = record(value, 'providers')
  // probes.providers 真实形状：status + providers 数组 [{provider, models}]
  return {
    status: text(data.status, 'providers.status', true),
    live_provider_availability_checked: boolean(
      data.live_provider_availability_checked,
      'providers.live_provider_availability_checked',
    ),
    providers: array(data.providers, 'providers.providers').map(
      (item, index) => {
        const row = record(item, `providers.providers.${index}`)
        return {
          provider: text(row.provider, `providers.providers.${index}.provider`),
          models:
            row.models === undefined || row.models === null
              ? []
              : array(row.models, `providers.providers.${index}.models`).map(
                  (model, modelIndex) =>
                    text(
                      model,
                      `providers.providers.${index}.models.${modelIndex}`,
                    ),
                ),
        }
      },
    ),
  }
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createMonitoringClient(http: AxiosInstance): MonitoringClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    params?: unknown,
    signal?: AbortSignal,
    timeout = 15_000,
  ): Promise<T> {
    return read(
      await http.get<unknown, unknown>(url, { params, signal, timeout }),
    )
  }
  return {
    systemStatus: async (signal) =>
      get('/system/status', systemStatus, undefined, signal, 20_000),
    apiStats: (windowSeconds, signal) =>
      get(
        '/metrics/api-stats',
        apiStats,
        { window_seconds: windowSeconds },
        signal,
      ),
    llmStats: (windowSeconds, signal) =>
      get(
        '/metrics/llm-stats',
        llmStats,
        windowSeconds === null ? {} : { window_seconds: windowSeconds },
        signal,
      ),
    cacheStats: (signal) =>
      get('/metrics/cache-stats', cacheStats, undefined, signal),
    sandboxConfig: (signal) =>
      get('/config/sandbox', sandboxConfig, undefined, signal),
    strategies: (signal) =>
      get('/config/strategies', strategies, undefined, signal),
    providers: (signal) =>
      get('/config/providers', providers, undefined, signal),
  }
}
