import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  ApiStats,
  CacheStats,
  LlmStats,
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
function nullableNumber(value: unknown, field: string): number | null {
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

function healthCheck(value: unknown, field: string) {
  const row = record(value, field)
  return {
    status: text(row.status, `${field}.status`, true),
    ...(row.detail !== undefined
      ? { detail: nullableText(row.detail, `${field}.detail`) ?? '' }
      : {}),
  }
}

function workersCheck(value: unknown, field: string) {
  const row = record(value, field)
  return {
    ...healthCheck(row, field),
    worker_count: nullableNumber(row.worker_count, `${field}.worker_count`),
    active: nullableNumber(row.active, `${field}.active`),
    reserved: nullableNumber(row.reserved, `${field}.reserved`),
    concurrency: nullableNumber(row.concurrency, `${field}.concurrency`),
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
        waiting: nullableNumber(redis.waiting, 'health.checks.redis.waiting'),
        queues:
          redis.queues === undefined || redis.queues === null
            ? null
            : (redis.queues as unknown[]).map((item, index) =>
                text(item, `health.checks.redis.queues.${index}`),
              ),
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
      total_bytes: nullableNumber(
        memory.total_bytes,
        'resources.memory.total_bytes',
      ),
      available_bytes: nullableNumber(
        memory.available_bytes,
        'resources.memory.available_bytes',
      ),
      used_bytes: nullableNumber(
        memory.used_bytes,
        'resources.memory.used_bytes',
      ),
      percent: nullableFloat(memory.percent, 'resources.memory.percent'),
    },
    disk: {
      status: text(disk.status, 'resources.disk.status', true),
      total_bytes: nullableNumber(
        disk.total_bytes,
        'resources.disk.total_bytes',
      ),
      used_bytes: nullableNumber(disk.used_bytes, 'resources.disk.used_bytes'),
      free_bytes: nullableNumber(disk.free_bytes, 'resources.disk.free_bytes'),
      percent: nullableFloat(disk.percent, 'resources.disk.percent'),
    },
  }
}

function countsMap(value: unknown, field: string): Record<string, number> {
  return Object.fromEntries(
    Object.entries(record(value, field)).map(([key, item]) => [
      key,
      count(item, `${field}.${key}`),
    ]),
  )
}

function queueMetrics(value: unknown): QueueMetrics {
  const data = record(value, 'queue_metrics')
  const broker = record(data.broker_queue, 'queue_metrics.broker_queue')
  const pending = record(
    data.database_pending,
    'queue_metrics.database_pending',
  )
  const reserved = record(data.worker_reserved, 'queue_metrics.worker_reserved')
  return {
    broker_queue: {
      status: text(broker.status, 'queue_metrics.broker_queue.status', true),
      waiting: nullableNumber(
        broker.waiting,
        'queue_metrics.broker_queue.waiting',
      ),
      queues:
        broker.queues === undefined || broker.queues === null
          ? null
          : (broker.queues as unknown[]).map((item, index) =>
              text(item, `queue_metrics.broker_queue.queues.${index}`),
            ),
    },
    database_pending: {
      status: text(
        pending.status,
        'queue_metrics.database_pending.status',
        true,
      ),
      count: nullableNumber(
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
      count: nullableNumber(
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
    task_count: count(data.task_count, 'system-status.task_count'),
    async_task_count: count(
      data.async_task_count,
      'system-status.async_task_count',
    ),
    task_counts: countsMap(data.task_counts, 'system-status.task_counts'),
    async_task_counts: countsMap(
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
    request_count: nullableNumber(
      data.request_count,
      'api-stats.request_count',
    ),
    errors: nullableNumber(data.errors, 'api-stats.errors'),
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

function llmStats(value: unknown): LlmStats {
  const data = record(value, 'llm-stats')
  return {
    total_calls: count(data.total_calls, 'llm-stats.total_calls'),
    successful_calls: count(
      data.successful_calls,
      'llm-stats.successful_calls',
    ),
    failed_calls: count(data.failed_calls, 'llm-stats.failed_calls'),
    success_rate: nullableFloat(data.success_rate, 'llm-stats.success_rate'),
    avg_latency_ms: nullableFloat(
      data.avg_latency_ms,
      'llm-stats.avg_latency_ms',
    ),
  }
}

function cacheStats(value: unknown): CacheStats {
  const data = record(value, 'cache-stats')
  return {
    enabled: boolean(data.enabled, 'cache-stats.enabled'),
    total_entries: count(data.total_entries, 'cache-stats.total_entries'),
    disk_usage_mb:
      nullableFloat(data.disk_usage_mb, 'cache-stats.disk_usage_mb') ?? 0,
    hit_rate: nullableFloat(data.hit_rate, 'cache-stats.hit_rate'),
    hits: count(data.hits, 'cache-stats.hits'),
    misses: count(data.misses, 'cache-stats.misses'),
    api_calls_saved: count(data.api_calls_saved, 'cache-stats.api_calls_saved'),
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
        : (data.allowed_imports as unknown[]).map((item, index) =>
            text(item, `sandbox-config.allowed_imports.${index}`),
          ),
  }
}

function strategies(value: unknown): StrategyInfo[] {
  const data = record(value, 'strategies-response')
  return (data.strategies as unknown[]).map((item, index) => {
    const row = record(item, `strategies.${index}`)
    return {
      name: text(row.name, `strategies.${index}.name`),
      defaults: record(row.defaults, `strategies.${index}.defaults`),
    }
  })
}

function providers(value: unknown): ProvidersCatalog {
  const data = record(value, 'providers')
  const providersRow = record(data.providers, 'providers.providers')
  return {
    available: boolean(data.available, 'providers.available'),
    providers: Object.fromEntries(
      Object.entries(providersRow).map(([key, item]) => {
        const row = record(item, `providers.providers.${key}`)
        return [
          key,
          {
            models:
              row.models === undefined || row.models === null
                ? []
                : (row.models as unknown[]).map((model, index) =>
                    text(model, `providers.providers.${key}.models.${index}`),
                  ),
            source: text(row.source, `providers.providers.${key}.source`, true),
          },
        ]
      }),
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
