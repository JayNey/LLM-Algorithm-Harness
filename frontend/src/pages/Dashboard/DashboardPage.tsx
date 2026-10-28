import { useTranslation } from 'react-i18next'
import { currentLanguage, t } from '../../i18n/core.ts'
import { Alert, Button, Empty, Progress, Skeleton } from 'antd'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { AxiosInstance } from 'axios'
import { useRole } from '@/auth/roleContext.ts'
import { createDashboardClient } from '@/evaluations/dashboard.ts'
import { evaluationLabel } from '@/evaluations/presentation.ts'
import type { Evaluation } from '@/evaluations/types.ts'
import { Icon } from '@/layouts/components/Icon.tsx'
import { probeStatusLabel, formatUptime } from '@/monitoring/presentation.ts'
import { useAuthStore } from '@/store/auth.ts'
import { useUiStore } from '@/store/ui.ts'
import '@/evaluations/workflow.css'

type DashboardClient = ReturnType<typeof createDashboardClient>

function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  refresh: number,
) {
  const [attempt, setAttempt] = useState(0)
  const [snapshot, setSnapshot] = useState<{
    load: typeof load
    refresh: number
    attempt: number
    data?: T
    error?: string
    updated: number | null
  }>()
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setSnapshot({
            load,
            refresh,
            attempt,
            data,
            updated: Date.now(),
          })
      },
      (failure: unknown) => {
        if (!controller.signal.aborted)
          setSnapshot({
            load,
            refresh,
            attempt,
            error:
              failure instanceof Error ? failure.message : '加载失败，请重试',
            updated: null,
          })
      },
    )
    return () => controller.abort()
  }, [load, refresh, attempt])
  const current =
    snapshot?.load === load &&
    snapshot.refresh === refresh &&
    snapshot.attempt === attempt
  return {
    data: current ? snapshot.data : undefined,
    error: current ? snapshot.error : undefined,
    updated: current ? snapshot.updated : null,
    loading: !current,
    retry: () => setAttempt((value) => value + 1),
  }
}

function Failure({ message, retry }: { message: string; retry: () => void }) {
  useTranslation()

  return (
    <Alert
      type="error"
      showIcon
      message={t(message)}
      action={<Button onClick={retry}>{t('重试')}</Button>}
    />
  )
}

function Metric({
  title,
  data,
  loading,
  error,
  retry,
  note,
  currency = false,
}: {
  title: string
  data?: number
  loading: boolean
  error?: string
  retry: () => void
  note: string
  currency?: boolean
}) {
  useTranslation()

  return (
    <div aria-busy={loading}>
      <span>{title}</span>
      {loading ? (
        <Skeleton.Input active size="small" />
      ) : error ? (
        <>
          <strong>—</strong>
          <Button size="small" onClick={retry}>
            {t('重试')}
            {title}
          </Button>
          <p role="alert">{t(error)}</p>
        </>
      ) : (
        <strong>
          {currency
            ? `$${data?.toFixed(6).replace(/\.?0+$/, '') || '0'}`
            : data}
          <small>{currency ? 'USD' : t('个任务')}</small>
        </strong>
      )}
      <p>{note}</p>
    </div>
  )
}

function TaskFocus({ task }: { task: Evaluation }) {
  useTranslation()

  const navigate = useNavigate()
  const design = useUiStore((state) => state.appearanceVariant)
  const detail = `/evaluations/${encodeURIComponent(task.evaluation_id)}`
  const title = task.model ?? t('模型未记录')
  const copy = (
    <>
      <h2>{title}</h2>
      <p>
        {task.strategy_names.join(' · ') || t('策略未记录')} ·{' '}
        {evaluationLabel(task)}
      </p>
      <Button onClick={() => void navigate(detail)}>
        {t('查看最近任务 ')}
        <Icon name="arrow" size={16} />
      </Button>
    </>
  )
  if (design === 'studio') {
    const date = new Date(task.created_at)
    return (
      <section
        className="design-focus studio-focus"
        aria-label={t('最近评估焦点')}
      >
        <div className="journal-date">
          <strong>{Number.isNaN(date.getTime()) ? '—' : date.getDate()}</strong>
          <span>
            {Number.isNaN(date.getTime())
              ? task.created_at
              : date.toLocaleDateString(currentLanguage())}
          </span>
          <small>{t('最近创建')}</small>
        </div>
        <div className="journal-copy">{copy}</div>
        <div className="method-list">
          <div>
            <span>{t('评估任务')}</span>
            <strong>{task.evaluation_id}</strong>
          </div>
          <div>
            <span>{t('执行进度')}</span>
            <strong>
              {task.execution_progress.completed_units} /{' '}
              {task.execution_progress.total_units}
            </strong>
          </div>
        </div>
      </section>
    )
  }
  if (design === 'precision')
    return (
      <section
        className="design-focus precision-focus"
        aria-label={t('最近评估焦点')}
      >
        <div className="precision-intro">{copy}</div>
        <div className="duel-models">
          <div className="duel-model">
            <p>{task.evaluation_id}</p>
            <strong>
              {task.execution_progress.percentage}
              <small>%</small>
            </strong>
            <span className="metric-caption">
              {t('执行进度 · ')}
              {task.execution_progress.completed_units} /{' '}
              {task.execution_progress.total_units}
            </span>
          </div>
        </div>
        <div className="precision-delta">
          <strong>{task.problem_count}</strong>
          <p>{t('道评估题目')}</p>
        </div>
      </section>
    )
  return (
    <section
      className="design-focus orbit-focus"
      aria-label={t('最近评估焦点')}
    >
      <div className="orbit-copy">
        {copy}
        <p>{task.evaluation_id}</p>
      </div>
      <div className="orbit-visual">
        <Progress
          type="circle"
          percent={task.execution_progress.percentage}
          size={120}
          status={task.status === 'failed' ? 'exception' : 'normal'}
        />
        <div>
          <strong>
            {task.execution_progress.completed_units}
            <small>
              {' '}
              / {task.execution_progress.total_units} {t(' 次执行')}
            </small>
          </strong>
          <span>
            {t('已记录费用 $')}
            {task.spent_usd.toFixed(6)}
          </span>
        </div>
      </div>
    </section>
  )
}

function RecentTasks({ tasks }: { tasks: Evaluation[] }) {
  useTranslation()

  if (!tasks.length)
    return (
      <Empty description={t('还没有评估任务')}>
        <Link to="/evaluations/new">{t('创建第一次评估')}</Link>
      </Empty>
    )
  return (
    <div
      className="evaluation-list-scroll"
      tabIndex={0}
      role="region"
      aria-label={t('最近评估列表，可横向滚动')}
    >
      <table className="evaluation-list-table" aria-label={t('最近评估')}>
        <thead>
          <tr>
            {[
              t('评估任务 / 模型'),
              t('策略 / 题目'),
              t('状态 / 进度'),
              t('已记录费用'),
              t('创建时间'),
            ].map((label) => (
              <th key={label} scope="col">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.evaluation_id}>
              <td>
                <Link
                  to={`/evaluations/${encodeURIComponent(task.evaluation_id)}`}
                >
                  {task.evaluation_id}
                </Link>
                <small>{task.model ?? t('模型未记录')}</small>
              </td>
              <td>
                {task.strategy_names.join('、') || t('策略未记录')}
                <small>
                  {task.problem_count} {t(' 道题')}
                </small>
              </td>
              <td>
                {evaluationLabel(task)}
                <small>
                  {task.execution_progress.completed_units} /{' '}
                  {task.execution_progress.total_units} {t(' 次执行 ·')}{' '}
                  {task.execution_progress.percentage}%
                </small>
              </td>
              <td>
                ${task.spent_usd.toFixed(6)}
                <small>USD</small>
              </td>
              <td>
                <time dateTime={task.created_at}>
                  {new Date(task.created_at).toLocaleString(currentLanguage())}
                </time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SystemPanel({
  client,
  refresh,
}: {
  client: DashboardClient
  refresh: number
}) {
  useTranslation()

  const { state, reload } = useRole()
  if (state.status === 'loading')
    return <p role="status">{t('正在确认系统状态访问权限…')}</p>
  if (state.status === 'error')
    return <Failure message={t('无法确认访问权限')} retry={reload} />
  if (state.role !== 'admin') return <p>{t('系统状态仅管理员可查看。')}</p>
  return <AdminSystem key={state.role} client={client} refresh={refresh} />
}
function AdminSystem({
  client,
  refresh,
}: {
  client: DashboardClient
  refresh: number
}) {
  useTranslation()

  const load = useMemo(
    () => (signal: AbortSignal) => client.system('admin', signal),
    [client],
  )
  const system = useResource(load, refresh)
  if (system.loading)
    return (
      <div aria-busy="true">
        <Skeleton active paragraph={{ rows: 4 }} />
      </div>
    )
  if (system.error)
    return <Failure message={t(system.error)} retry={system.retry} />
  const data = system.data
  if (!data) return null
  const rows = [
    [t('整体'), data.health.status],
    [t('数据库'), data.health.checks.database.status],
    ['Redis', data.health.checks.redis.status],
    ['Workers', data.health.checks.workers.status],
    [t('沙箱'), data.health.checks.sandbox.status],
  ]
  return (
    <>
      <dl className="detail-list">
        {rows.map(([label, status]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {status === 'healthy' ? t('正常') : probeStatusLabel(status)}
            </dd>
          </div>
        ))}
      </dl>
      <p>
        {t('运行时间：')}
        {formatUptime(data.uptime_seconds)}
      </p>
      <p className="muted">
        {t('读取于 ')}
        {system.updated === null
          ? '—'
          : new Date(system.updated).toLocaleString(currentLanguage())}
      </p>
      <Link to="/settings/system">
        {t('查看系统监控 ')}
        <Icon name="arrow" size={16} />
      </Link>
    </>
  )
}

function Dashboard() {
  useTranslation()

  const navigate = useNavigate()
  const [client] = useState(() =>
    createDashboardClient(
      useAuthStore.getState().httpClient() as AxiosInstance,
    ),
  )
  const [refresh, setRefresh] = useState(0)
  const loads = useMemo(
    () => ({
      running: (signal: AbortSignal) => client.count('running', signal),
      completed: (signal: AbortSignal) => client.count('completed', signal),
    }),
    [client],
  )
  const recent = useResource(client.recent, refresh)
  const running = useResource(loads.running, refresh)
  const completed = useResource(loads.completed, refresh)
  const cost = useResource(client.cost, refresh)
  return (
    <div className="mock-business evaluation-workflow dashboard-page">
      <div className="page-heading">
        <div>
          <h1>{t('仪表盘')}</h1>
          <p>{t('当前账号的评估记录与系统概览。')}</p>
        </div>
        <div className="page-actions">
          <Button onClick={() => setRefresh((value) => value + 1)}>
            {t('刷新数据')}
          </Button>
          <Button
            type="primary"
            onClick={() => void navigate('/evaluations/new')}
          >
            <Icon name="plus" size={16} />
            {t('创建评估')}
          </Button>
        </div>
      </div>
      {recent.data?.items[0] && <TaskFocus task={recent.data.items[0]} />}
      <div className="metric-strip" aria-label={t('当前用户统计')}>
        <Metric
          title={t('评估总数')}
          {...recent}
          data={recent.data?.total}
          note={t('当前账号全部评估')}
        />
        <Metric
          title={t('运行中的评估')}
          {...running}
          note={t('当前账号 · running')}
        />
        <Metric
          title={t('已完成的评估')}
          {...completed}
          note={t('当前账号 · completed')}
        />
        <Metric
          title={t('累计调用费用')}
          {...cost}
          note={t('评估与已完成基准 · 已记录费用')}
          currency
        />
      </div>
      <div className="work-grid">
        <section className="panel recent">
          <div className="section-head">
            <div>
              <h2>{t('最近评估')}</h2>
              <p>{t('按创建时间倒序 · 最近 5 条')}</p>
            </div>
            <Link to="/evaluations">
              {t('全部任务 ')}
              <Icon name="arrow" size={16} />
            </Link>
          </div>
          {recent.loading ? (
            <div className="p-5" aria-busy="true">
              <Skeleton active paragraph={{ rows: 5 }} />
            </div>
          ) : recent.error ? (
            <Failure message={t(recent.error)} retry={recent.retry} />
          ) : recent.data ? (
            <RecentTasks tasks={recent.data.items} />
          ) : null}
          {recent.updated && (
            <div className="panel-footer">
              <Icon name="clock" size={14} />
              {t('读取于 ')}
              {recent.updated === null
                ? '—'
                : new Date(recent.updated).toLocaleString(
                    currentLanguage(),
                  )}{' '}
              {t(' · 手动刷新更新')}
            </div>
          )}
        </section>
        <aside className="insights">
          <section className="panel">
            <div className="section-head">
              <h2>{t('系统状态')}</h2>
            </div>
            <div className="p-5 pt-0">
              <SystemPanel client={client} refresh={refresh} />
            </div>
          </section>
          <section className="panel">
            <div className="section-head">
              <h2>{t('统计口径')}</h2>
            </div>
            <div className="p-5 pt-0">
              <p>{t('任务计数仅包含当前账号的评估。')}</p>
              <p>
                {t(
                  '累计费用包含当前账号的评估与已完成基准运行的已记录费用， 未包含实验与 A/B；未记录成本不代表免费。',
                )}
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}

export default function DashboardPage(): ReactNode {
  useTranslation()

  const owner = useAuthStore((state) => state.session?.marker ?? null)
  return owner ? <Dashboard key={owner} /> : <Skeleton active />
}
