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
    updated: string
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
            updated: new Date().toLocaleString(),
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
            updated: '',
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
    updated: current ? snapshot.updated : '',
    loading: !current,
    retry: () => setAttempt((value) => value + 1),
  }
}

function Failure({ message, retry }: { message: string; retry: () => void }) {
  return (
    <Alert
      type="error"
      showIcon
      message={message}
      action={<Button onClick={retry}>重试</Button>}
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
  return (
    <div aria-busy={loading}>
      <span>{title}</span>
      {loading ? (
        <Skeleton.Input active size="small" />
      ) : error ? (
        <>
          <strong>—</strong>
          <Button size="small" onClick={retry}>
            重试{title}
          </Button>
          <p role="alert">{error}</p>
        </>
      ) : (
        <strong>
          {currency
            ? `$${data?.toFixed(6).replace(/\.?0+$/, '') || '0'}`
            : data}
          <small>{currency ? 'USD' : '个任务'}</small>
        </strong>
      )}
      <p>{note}</p>
    </div>
  )
}

function TaskFocus({ task }: { task: Evaluation }) {
  const navigate = useNavigate()
  const design = useUiStore((state) => state.appearanceVariant)
  const detail = `/evaluations/${encodeURIComponent(task.evaluation_id)}`
  const title = task.model ?? '模型未记录'
  const copy = (
    <>
      <h2>{title}</h2>
      <p>
        {task.strategy_names.join(' · ') || '策略未记录'} ·{' '}
        {evaluationLabel(task)}
      </p>
      <Button onClick={() => void navigate(detail)}>
        查看最近任务 <Icon name="arrow" size={16} />
      </Button>
    </>
  )
  if (design === 'studio') {
    const date = new Date(task.created_at)
    return (
      <section className="design-focus studio-focus" aria-label="最近评估焦点">
        <div className="journal-date">
          <strong>{Number.isNaN(date.getTime()) ? '—' : date.getDate()}</strong>
          <span>
            {Number.isNaN(date.getTime())
              ? task.created_at
              : date.toLocaleDateString()}
          </span>
          <small>最近创建</small>
        </div>
        <div className="journal-copy">{copy}</div>
        <div className="method-list">
          <div>
            <span>评估任务</span>
            <strong>{task.evaluation_id}</strong>
          </div>
          <div>
            <span>执行进度</span>
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
        aria-label="最近评估焦点"
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
              执行进度 · {task.execution_progress.completed_units} /{' '}
              {task.execution_progress.total_units}
            </span>
          </div>
        </div>
        <div className="precision-delta">
          <strong>{task.problem_count}</strong>
          <p>道评估题目</p>
        </div>
      </section>
    )
  return (
    <section className="design-focus orbit-focus" aria-label="最近评估焦点">
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
            <small> / {task.execution_progress.total_units} 次执行</small>
          </strong>
          <span>已记录费用 ${task.spent_usd.toFixed(6)}</span>
        </div>
      </div>
    </section>
  )
}

function RecentTasks({ tasks }: { tasks: Evaluation[] }) {
  if (!tasks.length)
    return (
      <Empty description="还没有评估任务">
        <Link to="/evaluations/new">创建第一次评估</Link>
      </Empty>
    )
  return (
    <div
      className="evaluation-list-scroll"
      tabIndex={0}
      role="region"
      aria-label="最近评估列表，可横向滚动"
    >
      <table className="evaluation-list-table" aria-label="最近评估">
        <thead>
          <tr>
            {[
              '评估任务 / 模型',
              '策略 / 题目',
              '状态 / 进度',
              '已记录费用',
              '创建时间',
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
                <small>{task.model ?? '模型未记录'}</small>
              </td>
              <td>
                {task.strategy_names.join('、') || '策略未记录'}
                <small>{task.problem_count} 道题</small>
              </td>
              <td>
                {evaluationLabel(task)}
                <small>
                  {task.execution_progress.completed_units} /{' '}
                  {task.execution_progress.total_units} 次执行 ·{' '}
                  {task.execution_progress.percentage}%
                </small>
              </td>
              <td>
                ${task.spent_usd.toFixed(6)}
                <small>USD</small>
              </td>
              <td>
                <time dateTime={task.created_at}>
                  {new Date(task.created_at).toLocaleString()}
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
  const { state, reload } = useRole()
  if (state.status === 'loading')
    return <p role="status">正在确认系统状态访问权限…</p>
  if (state.status === 'error')
    return <Failure message="无法确认访问权限" retry={reload} />
  if (state.role !== 'admin') return <p>系统状态仅管理员可查看。</p>
  return <AdminSystem key={state.role} client={client} refresh={refresh} />
}
function AdminSystem({
  client,
  refresh,
}: {
  client: DashboardClient
  refresh: number
}) {
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
    return <Failure message={system.error} retry={system.retry} />
  const data = system.data
  if (!data) return null
  const rows = [
    ['整体', data.health.status],
    ['数据库', data.health.checks.database.status],
    ['Redis', data.health.checks.redis.status],
    ['Workers', data.health.checks.workers.status],
    ['沙箱', data.health.checks.sandbox.status],
  ]
  return (
    <>
      <dl className="detail-list">
        {rows.map(([label, status]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{status === 'healthy' ? '正常' : probeStatusLabel(status)}</dd>
          </div>
        ))}
      </dl>
      <p>运行时间：{formatUptime(data.uptime_seconds)}</p>
      <p className="muted">读取于 {system.updated}</p>
      <Link to="/settings/system">
        查看系统监控 <Icon name="arrow" size={16} />
      </Link>
    </>
  )
}

function Dashboard() {
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
          <h1>仪表盘</h1>
          <p>当前账号的评估记录与系统概览。</p>
        </div>
        <div className="page-actions">
          <Button onClick={() => setRefresh((value) => value + 1)}>
            刷新数据
          </Button>
          <Button
            type="primary"
            onClick={() => void navigate('/evaluations/new')}
          >
            <Icon name="plus" size={16} />
            创建评估
          </Button>
        </div>
      </div>
      {recent.data?.items[0] && <TaskFocus task={recent.data.items[0]} />}
      <div className="metric-strip" aria-label="当前用户统计">
        <Metric
          title="评估总数"
          {...recent}
          data={recent.data?.total}
          note="当前账号全部评估"
        />
        <Metric title="运行中的评估" {...running} note="当前账号 · running" />
        <Metric
          title="已完成的评估"
          {...completed}
          note="当前账号 · completed"
        />
        <Metric
          title="累计调用费用"
          {...cost}
          note="评估与已完成基准 · 已记录费用"
          currency
        />
      </div>
      <div className="work-grid">
        <section className="panel recent">
          <div className="section-head">
            <div>
              <h2>最近评估</h2>
              <p>按创建时间倒序 · 最近 5 条</p>
            </div>
            <Link to="/evaluations">
              全部任务 <Icon name="arrow" size={16} />
            </Link>
          </div>
          {recent.loading ? (
            <div className="p-5" aria-busy="true">
              <Skeleton active paragraph={{ rows: 5 }} />
            </div>
          ) : recent.error ? (
            <Failure message={recent.error} retry={recent.retry} />
          ) : recent.data ? (
            <RecentTasks tasks={recent.data.items} />
          ) : null}
          {recent.updated && (
            <div className="panel-footer">
              <Icon name="clock" size={14} />
              读取于 {recent.updated} · 手动刷新更新
            </div>
          )}
        </section>
        <aside className="insights">
          <section className="panel">
            <div className="section-head">
              <h2>系统状态</h2>
            </div>
            <div className="p-5 pt-0">
              <SystemPanel client={client} refresh={refresh} />
            </div>
          </section>
          <section className="panel">
            <div className="section-head">
              <h2>统计口径</h2>
            </div>
            <div className="p-5 pt-0">
              <p>任务计数仅包含当前账号的评估。</p>
              <p>
                累计费用包含当前账号的评估与已完成基准运行的已记录费用，
                未包含实验与 A/B；未记录成本不代表免费。
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}

export default function DashboardPage(): ReactNode {
  const owner = useAuthStore((state) => state.session?.marker ?? null)
  return owner ? <Dashboard key={owner} /> : <Skeleton active />
}
