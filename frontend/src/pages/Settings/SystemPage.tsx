import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Descriptions, Skeleton, Switch, Tabs } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AxiosInstance } from 'axios'
import { ApiClientError } from '@/auth/http.ts'
import { useRole } from '@/auth/roleContext.ts'
import { useAuthStore } from '@/store/auth.ts'
import { createMonitoringClient } from '@/monitoring/client.ts'
import type {
  ApiStats,
  CacheStats,
  LlmStats,
  ProvidersCatalog,
  StrategyInfo,
  SystemStatus,
} from '@/monitoring/types.ts'
import {
  formatBytes,
  formatMs,
  formatPercent,
  formatRatePerSecond,
  formatUptime,
  probeStatusLabel,
} from '@/monitoring/presentation.ts'

const REFRESH_MS = 30_000
const WINDOW_OPTIONS = [
  {
    value: 60,
    get label() {
      return t('最近 1 分钟')
    },
  },
  {
    value: 300,
    get label() {
      return t('最近 5 分钟')
    },
  },
  {
    value: 3600,
    get label() {
      return t('最近 1 小时')
    },
  },
  {
    value: 86400,
    get label() {
      return t('最近 24 小时')
    },
  },
]

function useResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{
    load: typeof load
    attempt: number
    data?: T
    error?: string
  }>()
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ load, attempt, data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            load,
            attempt,
            error: error instanceof Error ? error.message : '加载失败，请重试',
          })
      },
    )
    return () => controller.abort()
  }, [load, attempt])
  const current = state?.load === load && state.attempt === attempt
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !current,
    retry: () => setAttempt((value) => value + 1),
  }
}

function HealthSection({ status }: { status: SystemStatus }) {
  useTranslation()

  const { checks } = status.health
  const rows: [string, string, string][] = [
    [t('整体'), probeStatusLabel(status.health.status), ''],
    [
      t('数据库'),
      probeStatusLabel(checks.database.status),
      checks.database.detail ?? '',
    ],
    ['Redis', probeStatusLabel(checks.redis.status), checks.redis.detail ?? ''],
    [
      'Workers',
      probeStatusLabel(checks.workers.status),
      checks.workers.worker_count !== null &&
      checks.workers.worker_count !== undefined
        ? t('{{value1}} 个（活跃 {{value2}}）', {
            value1: checks.workers.worker_count,
            value2: checks.workers.active ?? '—',
          })
        : (checks.workers.detail ?? ''),
    ],
    [
      t('沙箱'),
      probeStatusLabel(checks.sandbox.status),
      checks.sandbox.detail ?? '',
    ],
  ]
  return (
    <table className="evaluation-list-table" aria-label={t('组件健康')}>
      <thead>
        <tr>
          {[t('组件'), t('状态'), t('说明')].map((name) => (
            <th key={name} scope="col">
              {name}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, state, detail]) => (
          <tr key={name}>
            <td>{name}</td>
            <td>{state}</td>
            <td>{detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ResourcesSection({ status }: { status: SystemStatus }) {
  useTranslation()

  const { cpu, memory, disk } = status.resources
  return (
    <Descriptions
      column={1}
      bordered
      size="small"
      items={[
        {
          key: 'cpu',
          label: 'CPU',
          children: t('{{value1}}（{{value2}}s 采样）', {
            value1: formatPercent(cpu.percent),
            value2: cpu.sample_seconds,
          }),
        },
        {
          key: 'memory',
          label: t('内存'),
          children: t('{{value1}} · 已用 {{value2}} / {{value3}}', {
            value1: formatPercent(memory.percent),
            value2: formatBytes(memory.used_bytes),
            value3: formatBytes(memory.total_bytes),
          }),
        },
        {
          key: 'disk',
          label: t('磁盘（上传区）'),
          children: t('{{value1}} · 已用 {{value2}} / {{value3}}', {
            value1: formatPercent(disk.percent),
            value2: formatBytes(disk.used_bytes),
            value3: formatBytes(disk.total_bytes),
          }),
        },
      ]}
    />
  )
}

function QueueSection({ status }: { status: SystemStatus }) {
  useTranslation()

  const { queue_metrics, task_counts, async_task_counts } = status
  const queueDetail =
    queue_metrics.broker_queue.waiting === null
      ? probeStatusLabel(queue_metrics.broker_queue.status)
      : t('{{value1}} 条{{value2}}', {
          value1: queue_metrics.broker_queue.waiting,
          value2: queue_metrics.broker_queue.queues
            ? `（${queue_metrics.broker_queue.queues
                .map((queue) => `${queue.name} ${queue.waiting ?? '?'}`)
                .join('、')}）`
            : '',
        })
  return (
    <Descriptions
      column={1}
      bordered
      size="small"
      items={[
        {
          key: 'waiting',
          label: t('Broker 等待队列'),
          children: queueDetail,
        },
        {
          key: 'pending',
          label: t('数据库待处理'),
          children:
            queue_metrics.database_pending.count === null
              ? probeStatusLabel(queue_metrics.database_pending.status)
              : t('{{value1}} 条', {
                  value1: queue_metrics.database_pending.count,
                }),
        },
        {
          key: 'reserved',
          label: t('Worker 已预留'),
          children:
            queue_metrics.worker_reserved.count === null
              ? probeStatusLabel(queue_metrics.worker_reserved.status)
              : t('{{value1}} 条', {
                  value1: queue_metrics.worker_reserved.count,
                }),
        },
        {
          key: 'tasks',
          label: t('评估任务计数'),
          children:
            task_counts === null
              ? t('业务库暂不可用')
              : Object.entries(task_counts)
                  .map(([key, value]) => `${key} ${value}`)
                  .join(' · '),
        },
        {
          key: 'async',
          label: t('异步任务计数'),
          children:
            async_task_counts === null
              ? t('业务库暂不可用')
              : Object.entries(async_task_counts)
                  .map(([key, value]) => `${key} ${value}`)
                  .join(' · '),
        },
      ]}
    />
  )
}

function StatsSection({
  api,
  llm,
  cache,
  windowSeconds,
  onWindowChange,
}: {
  api: ApiStats | undefined
  llm: LlmStats | undefined
  cache: CacheStats | undefined
  windowSeconds: number
  onWindowChange: (value: number) => void
}) {
  useTranslation()

  return (
    <div>
      <label className="evaluation-section-heading">
        {t('统计窗口')}
        <select
          aria-label={t('统计窗口')}
          value={windowSeconds}
          onChange={(event) => onWindowChange(Number(event.target.value))}
        >
          {WINDOW_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <Descriptions
        column={1}
        bordered
        size="small"
        title={t('API 请求')}
        items={[
          {
            key: 'requests',
            label: t('请求数 / QPS'),
            children: `${api?.request_count ?? '—'} · ${formatRatePerSecond(api?.requests_per_second ?? null)}`,
          },
          {
            key: 'latency',
            label: t('平均 / P95 响应'),
            children: `${formatMs(api?.avg_response_time_ms ?? null)} · ${formatMs(api?.p95_response_time_ms ?? null)}`,
          },
          {
            key: 'errors',
            label: t('错误数 / 错误率'),
            children: `${api?.errors ?? '—'} · ${formatPercent(api?.error_rate ?? null)}`,
          },
        ]}
      />
      <Descriptions
        column={1}
        bordered
        size="small"
        title={t('LLM 调用')}
        items={[
          {
            key: 'calls',
            label: t('总调用 / 成功 / 失败'),
            children: (() => {
              if (!llm) return '—'
              // 窗口不完整时字段为 null——回退 retained_sample 并标注
              const sample =
                llm.total_calls === null && llm.retained_sample
                  ? llm.retained_sample
                  : llm
              const suffix =
                llm.total_calls === null && llm.retained_sample
                  ? t('（部分样本）')
                  : ''
              return `${sample.total_calls ?? '—'} / ${sample.successful_calls ?? '—'} / ${sample.failed_calls ?? '—'}${suffix}`
            })(),
          },
          {
            key: 'success',
            label: t('成功率 / 平均延迟'),
            children: (() => {
              if (!llm) return '— · —'
              const sample =
                llm.success_rate === null && llm.retained_sample
                  ? llm.retained_sample
                  : llm
              return `${formatPercent(sample.success_rate)} · ${formatMs(sample.avg_latency_ms)}`
            })(),
          },
        ]}
      />
      <Descriptions
        column={1}
        bordered
        size="small"
        title={t('响应缓存（跨 worker）')}
        items={[
          {
            key: 'cache-enabled',
            label: t('状态'),
            children: (() => {
              if (!cache) return '—'
              if (cache.enabled === null) return probeStatusLabel(cache.status)
              return cache.enabled ? t('已启用') : t('未启用')
            })(),
          },
          {
            key: 'cache-hits',
            label: t('命中 / 未命中 / 命中率'),
            children: cache
              ? `${cache.hits ?? '—'} / ${cache.misses ?? '—'} · ${formatPercent(cache.hit_rate)}`
              : '—',
          },
          {
            key: 'cache-size',
            label: t('条目 / 磁盘占用'),
            children: cache
              ? `${cache.total_entries ?? '—'} · ${
                  cache.disk_usage_mb === null
                    ? '—'
                    : formatBytes(Math.round(cache.disk_usage_mb * 1024 * 1024))
                }`
              : '—',
          },
        ]}
      />
    </div>
  )
}

function ConfigSection() {
  useTranslation()

  const client = useMemo(
    () =>
      createMonitoringClient(
        useAuthStore.getState().httpClient() as AxiosInstance,
      ),
    [],
  )
  const sandbox = useResource(
    useCallback(
      (signal: AbortSignal) => client.sandboxConfig(signal),
      [client],
    ),
  )
  const strategies = useResource(
    useCallback((signal: AbortSignal) => client.strategies(signal), [client]),
  )
  const providers = useResource(
    useCallback((signal: AbortSignal) => client.providers(signal), [client]),
  )
  return (
    <div>
      <h3>{t('沙箱配置（只读）')}</h3>
      {sandbox.loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : sandbox.error ? (
        <Alert type="error" message={t(sandbox.error)} />
      ) : sandbox.data ? (
        <Descriptions
          column={1}
          bordered
          size="small"
          items={[
            {
              key: 'backend',
              label: t('后端'),
              children: sandbox.data.backend,
            },
            {
              key: 'image',
              label: t('镜像'),
              children: sandbox.data.docker_image,
            },
            {
              key: 'timeout',
              label: t('超时 / 内存 / 进程'),
              children: `${sandbox.data.timeout_seconds}s · ${sandbox.data.memory_limit_mb}MB · ${sandbox.data.max_processes}`,
            },
            {
              key: 'imports',
              label: t('允许导入'),
              children: sandbox.data.allowed_imports.join('、') || '—',
            },
          ]}
        />
      ) : null}
      <h3>{t('策略列表')}</h3>
      {strategies.loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : strategies.data ? (
        <ul>
          {strategies.data.map((strategy: StrategyInfo) => (
            <li key={strategy.name}>{strategy.name}</li>
          ))}
        </ul>
      ) : (
        <p role="status">{t('暂无策略数据。')}</p>
      )}
      <h3>{t('提供商目录（离线示例）')}</h3>
      {providers.loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : providers.data ? (
        <ul>
          {providers.data.providers.map(
            (entry: ProvidersCatalog['providers'][number]) => (
              <li key={entry.provider}>
                {entry.provider}：{entry.models.join('、') || t('无示例模型')}
              </li>
            ),
          )}
        </ul>
      ) : (
        <p role="status">{t('暂无提供商数据。')}</p>
      )}
    </div>
  )
}

export default function SystemPage() {
  useTranslation()

  const { reload } = useRole()
  const client = useMemo(
    () =>
      createMonitoringClient(
        useAuthStore.getState().httpClient() as AxiosInstance,
      ),
    [],
  )
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [windowSeconds, setWindowSeconds] = useState(3600)
  const [attempt, setAttempt] = useState(0)
  const [denied, setDenied] = useState(false)
  const [snapshot, setSnapshot] = useState<SystemStatus | null>(null)
  const [apiStats, setApiStats] = useState<ApiStats | undefined>()
  const [llmStats, setLlmStats] = useState<LlmStats | undefined>()
  const [cacheStats, setCacheStats] = useState<CacheStats | undefined>()
  const [error, setError] = useState('')
  const generation = useRef(0)

  const refresh = useCallback(
    async (signal: AbortSignal) => {
      const operation = ++generation.current
      try {
        const [status, api, llm, cache] = await Promise.all([
          client.systemStatus(signal),
          client.apiStats(windowSeconds, signal),
          client.llmStats(windowSeconds, signal),
          client.cacheStats(signal),
        ])
        if (signal.aborted || operation !== generation.current) return
        setSnapshot(status)
        setApiStats(api)
        setLlmStats(llm)
        setCacheStats(cache)
        setError('')
      } catch (failure) {
        if (signal.aborted || operation !== generation.current) return
        if (failure instanceof ApiClientError && failure.status === 403) {
          setDenied(true)
          reload()
        } else {
          setError(
            failure instanceof Error
              ? failure.message
              : '暂时无法获取系统状态。',
          )
        }
      }
    },
    [client, windowSeconds, reload],
  )

  useEffect(() => {
    if (denied) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | null = null
    let cancelled = false
    const schedule = () => {
      // P1 修复：关闭自动刷新后不再续排（此前开关无效）
      if (cancelled || !autoRefresh) return
      if (document.visibilityState === 'hidden') {
        document.addEventListener('visibilitychange', onVisible, { once: true })
        return
      }
      timer = setTimeout(() => {
        void refresh(controller.signal).then(schedule)
      }, REFRESH_MS)
    }
    const onVisible = () => schedule()
    // 首刷经宏任务排程（effect 体内不做同步 setState 调用）
    timer = setTimeout(() => void refresh(controller.signal).then(schedule), 0)
    return () => {
      cancelled = true
      controller.abort()
      if (timer !== null) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refresh, autoRefresh, denied, attempt])

  if (denied) {
    return (
      <section className="mx-auto w-full max-w-2xl">
        <Alert type="error" message={t('无权访问此页面')} showIcon />
        <p className="mt-6">
          <Link to="/settings">{t('返回设置')}</Link>
        </p>
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-3xl">
      <h1 className="mb-2 text-xl font-semibold">{t('系统状态')}</h1>
      <p className="mb-4 text-neutral-600 dark:text-neutral-400">
        {t('仅管理员可查看。数据来自只读监控端点；统计范围为当前 API 进程。')}
      </p>
      <div className="evaluation-section-heading mb-4">
        <label>
          {t('自动刷新（30 秒，页面隐藏时暂停）')}
          <Switch
            aria-label={t('自动刷新')}
            checked={autoRefresh}
            onChange={setAutoRefresh}
          />
        </label>
        <Button
          aria-label={t('立即刷新')}
          onClick={() => setAttempt((v) => v + 1)}
        >
          {t('立即刷新')}
        </Button>
      </div>
      {error && (
        <Alert
          type="error"
          message={t(error)}
          showIcon
          className="mb-4"
          action={
            <Button onClick={() => setAttempt((value) => value + 1)}>
              {t('重试')}
            </Button>
          }
        />
      )}
      {snapshot ? (
        <Tabs
          items={[
            {
              key: 'overview',
              label: t('概览'),
              children: (
                <div className="grid gap-6">
                  <Descriptions
                    column={1}
                    bordered
                    size="small"
                    items={[
                      {
                        key: 'uptime',
                        label: t('运行时间'),
                        children: formatUptime(snapshot.uptime_seconds),
                      },
                      {
                        key: 'tasks',
                        label: t('评估 / 异步任务总数'),
                        children: `${snapshot.task_count ?? t('不可用')} / ${snapshot.async_task_count ?? t('不可用')}`,
                      },
                    ]}
                  />
                  <HealthSection status={snapshot} />
                </div>
              ),
            },
            {
              key: 'resources',
              label: t('资源'),
              children: <ResourcesSection status={snapshot} />,
            },
            {
              key: 'queue',
              label: t('队列与任务'),
              children: <QueueSection status={snapshot} />,
            },
            {
              key: 'stats',
              label: t('统计'),
              children: (
                <StatsSection
                  api={apiStats}
                  llm={llmStats}
                  cache={cacheStats}
                  windowSeconds={windowSeconds}
                  onWindowChange={setWindowSeconds}
                />
              ),
            },
            {
              key: 'config',
              label: t('配置'),
              children: <ConfigSection />,
            },
          ]}
        />
      ) : (
        <div aria-busy="true">
          <p role="status">{t('正在加载系统状态…')}</p>
          <Skeleton active paragraph={{ rows: 8 }} />
        </div>
      )}
      <p className="mt-6">
        <Link to="/settings">{t('返回设置')}</Link>
      </p>
    </section>
  )
}
