import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createMonitoringClient } from './client.ts'

// 形状取自 api/monitoring/{service,probes,store,queue_probe}.py 的真实响应
// （system/status 路由拼装 + probes + queue_probe 子进程）。
function systemStatusFixture() {
  return {
    uptime_seconds: 123.4,
    scope: 'current_api_process',
    task_counts: { pending: 1, running: 2, completed: 3 },
    task_count: 6,
    task_status: 'ok',
    task_source: 'monitor_store',
    async_task_counts: { pending: 1, running: 0, completed: 5 },
    async_task_count: 6,
    async_task_status: 'ok',
    async_task_source: 'async_task',
    health: {
      status: 'healthy',
      scope: 'configured_api_foundation',
      checks: {
        database: {
          status: 'ok',
          components: {
            authentication: { status: 'ok' },
            files: { status: 'ok' },
            business_database: { status: 'ok' },
          },
        },
        redis: {
          status: 'ok',
          broker_queue: {
            status: 'ok',
            reason: 'observed',
            waiting: 3,
            queues: [
              { name: 'default', waiting: 1 },
              { name: 'evaluations', waiting: 2 },
            ],
          },
        },
        workers: {
          status: 'ok',
          worker_count: 2,
          active: 1,
          reserved: 0,
          concurrency: 4,
        },
        sandbox: { status: 'ok' },
      },
      pending_issues: [157],
    },
    resources: {
      scope: 'api_host',
      cpu: { status: 'ok', percent: 12.5, sample_seconds: 0.1 },
      memory: {
        status: 'ok',
        total_bytes: 16000000000,
        available_bytes: 8000000000,
        used_bytes: 8000000000,
        percent: 50.0,
      },
      disk: {
        status: 'ok',
        scope: 'upload_filesystem',
        total_bytes: 500000000000,
        used_bytes: 250000000000,
        free_bytes: 250000000000,
        percent: 50.0,
      },
    },
    workers: {
      status: 'ok',
      worker_count: 2,
      active: 1,
      reserved: 0,
      concurrency: 4,
    },
    queue_metrics: {
      broker_queue: {
        status: 'ok',
        reason: 'observed',
        waiting: 3,
        queues: [
          { name: 'default', waiting: 1 },
          { name: 'evaluations', waiting: 2 },
        ],
      },
      database_pending: { status: 'ok', source: 'async_task', count: 1 },
      worker_reserved: {
        status: 'ok',
        source: 'responding_celery_workers',
        count: 0,
      },
    },
    containers: { status: 'not_configured' },
  }
}

function clientFor(reply: (config: { url: string }) => unknown) {
  return createMonitoringClient({
    get: async (url: string, config?: { params?: unknown }) => {
      return (reply({ url, ...config }) as { data: unknown }).data
    },
  } as never)
}

test('system/status 全量解析（健康/资源/队列对象/worker）', async () => {
  const client = clientFor(({ url }) => {
    assert.equal(url, '/system/status')
    return { data: systemStatusFixture() }
  })
  const status = await client.systemStatus()
  assert.equal(status.health.checks.workers.worker_count, 2)
  assert.equal(
    status.health.checks.database.components?.authentication.status,
    'ok',
  )
  assert.equal(status.resources.cpu.percent, 12.5)
  // broker_queue.queues 是 [{name, waiting}] 对象数组
  assert.deepEqual(status.queue_metrics.broker_queue.queues, [
    { name: 'default', waiting: 1 },
    { name: 'evaluations', waiting: 2 },
  ])
  assert.equal(status.queue_metrics.database_pending.count, 1)
  assert.deepEqual(status.task_counts, { pending: 1, running: 2, completed: 3 })
})

test('status 降级形态：workers unknown、业务库不可用、队列未知', async () => {
  const fixture = systemStatusFixture()
  fixture.health.checks.workers = { status: 'unknown' }
  fixture.resources.cpu = {
    status: 'unknown',
    percent: null,
    sample_seconds: 0.1,
  }
  // 业务库不可用：total/counts 透传 null
  fixture.task_count = null
  fixture.task_counts = null
  fixture.async_task_count = null
  fixture.async_task_counts = null
  fixture.queue_metrics.broker_queue = {
    status: 'unknown',
    waiting: null,
    queues: null,
  }
  const client = clientFor(() => ({ data: fixture }))
  const status = await client.systemStatus()
  assert.equal(status.task_count, null)
  assert.equal(status.task_counts, null)
  assert.equal(status.health.checks.workers.worker_count, null)
  assert.equal(status.resources.cpu.percent, null)
  assert.equal(status.queue_metrics.broker_queue.waiting, null)
})

test('api-stats 窗口统计解析（可空指标 + 窗口字段）', async () => {
  const client = clientFor(({ params }) => {
    assert.deepEqual(params, { window_seconds: 3600 })
    return {
      data: {
        request_count: 120,
        errors: 3,
        error_rate: 0.025,
        avg_response_time_ms: 42.5,
        p95_response_time_ms: 180.2,
        requests_per_second: 0.033,
        source: 'persisted_requests',
        window_complete: true,
        window_seconds: 3600,
        retention_seconds: 604800,
        max_rows: 10000,
        started_at: 1,
        pruned_through: null,
        capture_gap_through: null,
        retained_sample: {},
        endpoints: [],
      },
    }
  })
  const stats = await client.apiStats(3600)
  assert.equal(stats.p95_response_time_ms, 180.2)
  assert.equal(stats.window_complete, true)
})

test('llm-stats 窗口不完整：五字段 null + retained_sample 回退', async () => {
  const client = clientFor(({ params }) => {
    assert.deepEqual(params, { window_seconds: 3600 })
    return {
      data: {
        status: 'ok',
        source: 'retained_sample',
        total_calls: null,
        successful_calls: null,
        failed_calls: null,
        success_rate: null,
        avg_latency_ms: null,
        window_seconds: 3600,
        window_complete: false,
        started_at: 100,
        pruned_through: null,
        retention_seconds: 604800,
        max_rows: 10000,
        retained_sample: {
          total_calls: 4,
          successful_calls: 3,
          failed_calls: 1,
          success_rate: 0.75,
          avg_latency_ms: 250,
        },
      },
    }
  })
  const stats = await client.llmStats(3600)
  assert.equal(stats.total_calls, null)
  assert.equal(stats.window_complete, false)
  assert.equal(stats.retained_sample?.total_calls, 4)
})

test('llm-stats 全量模式解析（rate 可空）', async () => {
  const client = clientFor(({ url }) => {
    assert.equal(url, '/metrics/llm-stats')
    return {
      data: {
        status: 'ok',
        total_calls: 10,
        successful_calls: 8,
        failed_calls: 2,
        success_rate: 0.8,
        avg_latency_ms: 320.5,
      },
    }
  })
  const llm = await client.llmStats(null)
  assert.equal(llm.success_rate, 0.8)
})

test('cache-stats 两种形态：正常观测与 not_configured', async () => {
  const normal = clientFor(() => ({
    data: {
      status: 'ok',
      enabled: true,
      total_entries: 40,
      disk_usage_mb: 1.2,
      hit_rate: 0.75,
      hits: 30,
      misses: 10,
      api_calls_saved: 30,
    },
  }))
  const cache = await normal.cacheStats()
  assert.equal(cache.enabled, true)
  assert.equal(cache.hit_rate, 0.75)

  // API-only 部署常态：仅 status+scope，数值字段缺失
  const notConfigured = clientFor(() => ({
    data: { status: 'not_configured', scope: 'shared_cache_observations' },
  }))
  const degraded = await notConfigured.cacheStats()
  assert.equal(degraded.status, 'not_configured')
  assert.equal(degraded.enabled, null)
  assert.equal(degraded.total_entries, null)

  // 共享观测非 fresh：数值可空
  const shared = clientFor(() => ({
    data: {
      status: 'unknown',
      scope: 'shared_cache_observations',
      enabled: null,
      total_entries: null,
      disk_usage_mb: null,
      hit_rate: null,
      hits: null,
      misses: null,
      api_calls_saved: null,
    },
  }))
  const unknownShape = await shared.cacheStats()
  assert.equal(unknownShape.enabled, null)
})

test('config 三端点解析（沙箱/策略/提供商数组形状）', async () => {
  const client = clientFor(({ url }) => {
    if (url === '/config/sandbox')
      return {
        data: {
          backend: 'docker',
          docker_image: 'python:3.11-slim',
          timeout_seconds: 5,
          memory_limit_mb: 256,
          max_output_bytes: 1024,
          max_processes: 1,
          allowed_imports: ['math', 'json'],
        },
      }
    if (url === '/config/strategies')
      return {
        data: {
          strategies: [
            {
              name: 'vanilla',
              defaults: { temperature: 0.7, max_tokens: 2000 },
            },
          ],
        },
      }
    // probes.providers 真实形状：status + 数组 [{provider, models}]
    return {
      data: {
        status: 'ok',
        scope: 'offline_example_catalog',
        live_provider_availability_checked: false,
        providers: [
          { provider: 'openai', models: ['gpt-4o-mini'] },
          { provider: 'siliconflow', models: [] },
        ],
      },
    }
  })
  const sandbox = await client.sandboxConfig()
  assert.deepEqual(sandbox.allowed_imports, ['math', 'json'])
  const strategies = await client.strategies()
  assert.equal(strategies[0].name, 'vanilla')
  const catalog = await client.providers()
  assert.equal(catalog.status, 'ok')
  assert.deepEqual(catalog.providers, [
    { provider: 'openai', models: ['gpt-4o-mini'] },
    { provider: 'siliconflow', models: [] },
  ])
})

test('缺字段或错类型明确拒绝', async () => {
  const broken = systemStatusFixture()
  delete (broken as Record<string, unknown>).health
  const client = clientFor(() => ({ data: broken }))
  await assert.rejects(client.systemStatus(), /监控接口响应格式不兼容/)
})
