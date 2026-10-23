import { Alert, Button, Select, Skeleton, Tabs } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  BarCompare,
  RadarChart,
  ScatterPlot,
} from '@/components/charts/CompareCharts.tsx'
import { WinRateHeatmap } from '@/components/charts/WinRateHeatmap.tsx'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import {
  formatAccuracy,
  formatDateTime,
  formatUsd,
  statusLabel,
} from '@/experiments/presentation.ts'
import { useExperimentSession } from '@/experiments/session.tsx'
import type {
  ComparisonReport,
  ExperimentJob,
  OptimizeAdvisory,
  PanelData,
  ParetoResult,
} from '@/experiments/types.ts'
import { useTaskProgress } from '@/experiments/useTaskProgress.ts'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
const ACTIVE = new Set(['pending', 'running', 'paused'])

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

function ConfigSummary({ job }: { job: ExperimentJob }) {
  const config = job.config
  return (
    <dl>
      <dt>数据集</dt>
      <dd>{config.dataset_path}</dd>
      <dt>模型</dt>
      <dd>
        {config.models
          .map(
            (model) =>
              `${model.model}${model.temperature !== undefined ? `（温度 ${model.temperature}）` : ''}`,
          )
          .join('、')}
      </dd>
      <dt>策略</dt>
      <dd>{config.strategies.map((strategy) => strategy.name).join('、')}</dd>
      <dt>执行</dt>
      <dd>
        {config.execution === 'parallel'
          ? `并行 ×${config.max_workers}`
          : '串行'}{' '}
        · 重复 {config.repeats} 次
      </dd>
      <dt>预算</dt>
      <dd>
        {config.budget === null
          ? '不限制'
          : Object.entries(config.budget)
              .map(([kind, value]) => `${kind} ≤ ${value}`)
              .join('，')}
      </dd>
    </dl>
  )
}

function ComparisonTab({ experimentId }: { experimentId: string }) {
  const { client } = useExperimentSession()
  const report = useResource(
    useCallback(
      (signal: AbortSignal) => client.comparison(experimentId, signal),
      [client, experimentId],
    ),
  )
  if (report.loading) return <Skeleton active paragraph={{ rows: 5 }} />
  if (report.error)
    return <Alert role="alert" type="error" message={report.error} />
  const data = report.data as ComparisonReport
  return (
    <div>
      <h3>组合指标</h3>
      <table className="evaluation-list-table" aria-label="组合指标表">
        <thead>
          <tr>
            {[
              '组合',
              '模型',
              '策略',
              '完成/总数',
              '通过率',
              '正式通过率',
              '成本',
            ].map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.combinations.map((row) => (
            <tr key={row.combo_id}>
              <td>{row.combo_id}</td>
              <td>{row.model}</td>
              <td>{row.strategy}</td>
              <td>
                {row.denominator.completed} / {row.denominator.total}
              </td>
              <td>
                {row.pass_rate_over_total === null
                  ? '—'
                  : formatAccuracy(row.pass_rate_over_total)}
              </td>
              <td>
                {row.formal.rate === null
                  ? '—'
                  : formatAccuracy(row.formal.rate)}
              </td>
              <td>{formatUsd(row.cost.total_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {Object.entries(data.model_comparison.strategies).map(
        ([strategy, group]) => (
          <section key={strategy}>
            <h3>胜率矩阵：{strategy}</h3>
            <WinRateHeatmap strategy={strategy} matrix={group.matrix} />
            <table className="evaluation-list-table" aria-label="显著性检验">
              <thead>
                <tr>
                  {['对比', '不一致对数', 'p 值', '显著', '说明'].map(
                    (name) => (
                      <th key={name} scope="col">
                        {name}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {group.significance.map((row, index) => (
                  <tr key={index}>
                    <td>{row.a && row.b ? `${row.a} vs ${row.b}` : '—'}</td>
                    <td>{row.discordant_pairs}</td>
                    <td>{row.p_value === null ? '—' : row.p_value}</td>
                    <td>
                      {row.significant === null
                        ? '—'
                        : row.significant
                          ? '显著（p<0.05）'
                          : '不显著'}
                    </td>
                    <td>{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ),
      )}
      <h3>成本效益</h3>
      <table className="evaluation-list-table" aria-label="成本效益表">
        <thead>
          <tr>
            {['模型', '解决题数', '总成本', '每美元解决题数'].map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.model_comparison.cost_effectiveness.map((row) => (
            <tr key={row.model}>
              <td>{row.model}</td>
              <td>{row.solved}</td>
              <td>{formatUsd(row.total_cost_usd)}</td>
              <td>{row.solved_per_usd}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PanelTab({ experimentId }: { experimentId: string }) {
  const { client } = useExperimentSession()
  const panel = useResource(
    useCallback(
      (signal: AbortSignal) => client.panel(experimentId, signal),
      [client, experimentId],
    ),
  )
  if (panel.loading) return <Skeleton active paragraph={{ rows: 5 }} />
  if (panel.error)
    return <Alert role="alert" type="error" message={panel.error} />
  const data = panel.data as PanelData
  return (
    <div>
      <h3>能力雷达</h3>
      <RadarChart labels={data.radar.labels} datasets={data.radar.datasets} />
      <h3>算法维度雷达</h3>
      <RadarChart
        labels={data.algorithm_radar.labels}
        datasets={data.algorithm_radar.datasets}
      />
      <h3>成本-通过率散点</h3>
      <ScatterPlot
        points={data.scatter.map((point) => ({
          label: point.label,
          x: point.x,
          y: point.y,
        }))}
        xName="总成本（USD）"
        yName="正式通过率"
      />
      <h3>资源消耗</h3>
      <BarCompare
        labels={data.bar.labels}
        series={[
          { name: '调用次数', values: data.bar.calls },
          { name: '耗时（秒）', values: data.bar.elapsed },
          { name: 'token 数', values: data.bar.tokens },
        ]}
      />
    </div>
  )
}

function ParetoTab({ experimentId }: { experimentId: string }) {
  const { client } = useExperimentSession()
  const [accuracyMetric, setAccuracyMetric] = useState<'overall' | 'formal'>(
    'overall',
  )
  const load = useCallback(
    async (signal: AbortSignal): Promise<ParetoResult> => {
      return client.pareto(experimentId, [], accuracyMetric, signal)
    },
    [client, experimentId, accuracyMetric],
  )
  const pareto = useResource(load)
  if (pareto.loading) return <Skeleton active paragraph={{ rows: 5 }} />
  if (pareto.error)
    return <Alert role="alert" type="error" message={pareto.error} />
  const data = pareto.data as ParetoResult
  return (
    <div>
      <label>
        准确率口径
        <Select
          aria-label="帕累托准确率口径"
          value={accuracyMetric}
          options={[
            { value: 'overall', label: 'overall' },
            { value: 'formal', label: 'formal' },
          ]}
          onChange={(value: 'overall' | 'formal') => setAccuracyMetric(value)}
        />
      </label>
      <ScatterPlot
        points={data.points.map((point) => ({
          label: point.id,
          x: point.mean_cost_usd,
          y: point.mean_accuracy,
        }))}
        highlightIds={data.frontier_ids}
        xName="平均成本（USD）"
        yName="平均准确率"
      />
      <p>
        前沿组合：
        {data.points
          .filter((point) => data.frontier_ids.includes(point.id))
          .map((point) => `${point.model} × ${point.strategy}`)
          .join('、') || '无'}
      </p>
      <table className="evaluation-list-table" aria-label="帕累托预算建议">
        <thead>
          <tr>
            {['预算（USD）', '可行', '推荐组合'].map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.budget_recommendations.map((row) => (
            <tr key={row.budget_usd}>
              <td>{row.budget_usd}</td>
              <td>{row.feasible ? '可行' : '不可行'}</td>
              <td>{row.point_id || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function OptimizeTab({ experimentId }: { experimentId: string }) {
  const { client } = useExperimentSession()
  const [objective, setObjective] = useState<
    'highest_accuracy' | 'best_value' | 'lowest_cost'
  >('best_value')
  const load = useCallback(
    async (signal: AbortSignal): Promise<OptimizeAdvisory> => {
      return client.optimize(experimentId, { objective }, signal)
    },
    [client, experimentId, objective],
  )
  const advisory = useResource(load)
  if (advisory.loading) return <Skeleton active paragraph={{ rows: 5 }} />
  if (advisory.error)
    return <Alert role="alert" type="error" message={advisory.error} />
  const data = advisory.data as OptimizeAdvisory
  const names: Record<string, string> = {
    highest_accuracy: '最高准确率',
    best_value: '最佳性价比',
    lowest_cost: '最低成本',
  }
  return (
    <div>
      <label>
        优化目标
        <Select
          aria-label="成本优化目标"
          value={objective}
          options={Object.entries(names).map(([value, label]) => ({
            value,
            label,
          }))}
          onChange={(
            value: 'highest_accuracy' | 'best_value' | 'lowest_cost',
          ) => setObjective(value)}
        />
      </label>
      <table className="evaluation-list-table" aria-label="优化建议">
        <thead>
          <tr>
            {['目标', '可行', '推荐组合', '准确率', '成本'].map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(data.recommendations).map(([key, recommendation]) => (
            <tr key={key}>
              <td>
                {names[recommendation.objective] ?? recommendation.objective}
              </td>
              <td>{recommendation.feasible ? '可行' : '不可行'}</td>
              <td>
                {recommendation.feasible
                  ? `${recommendation.model ?? '—'} × ${recommendation.strategy ?? '—'}`
                  : (recommendation.note ?? '—')}
              </td>
              <td>
                {recommendation.accuracy !== undefined
                  ? formatAccuracy(recommendation.accuracy)
                  : '—'}
              </td>
              <td>
                {recommendation.cost_usd !== undefined
                  ? formatUsd(recommendation.cost_usd)
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>组合排名</h3>
      <table className="evaluation-list-table" aria-label="组合排名">
        <thead>
          <tr>
            {['模型', '策略', '准确率', '成本', '每美元解决'].map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.ranking.ranking.map((row) => (
            <tr key={`${row.model}-${row.strategy}`}>
              <td>{row.model}</td>
              <td>{row.strategy}</td>
              <td>
                {row.accuracy === null ? '—' : formatAccuracy(row.accuracy)}
              </td>
              <td>
                {row.cost_usd === null ? '成本未知' : formatUsd(row.cost_usd)}
              </td>
              <td>{row.ratio === null ? '—' : row.ratio}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ExperimentDetailPage() {
  const { experimentId } = useParams()
  const { client, owner } = useExperimentSession()
  const navigate = useNavigate()
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(
    (signal: AbortSignal) => client.get(experimentId ?? '', signal),
    [client, experimentId],
  )
  const jobResource = useResource(load)
  const job = jobResource.data
  const taskId = useResource(
    useCallback(
      async (signal: AbortSignal): Promise<string | null> => {
        if (!job || !ACTIVE.has(job.status)) return null
        const running = await client.runningExperimentTasks(signal)
        const match = running.find((task) => task.entity_id === job.id)
        return match ? match.id : null
      },
      [client, job],
    ),
  )
  const [started, setStarted] = useState<{ id: string; taskId: string } | null>(
    null,
  )
  const activeTaskId =
    (started && started.id === job?.id ? started.taskId : null) ??
    taskId.data ??
    null
  const progress = useTaskProgress(client, activeTaskId, owner)

  async function start() {
    if (!job || busy) return
    setBusy(true)
    setActionError(null)
    try {
      const startedJob = await client.run(job.id)
      setStarted({ id: job.id, taskId: startedJob.task_id })
      jobResource.retry()
      taskId.retry()
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '启动失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }
  async function cancel() {
    if (!activeTaskId || busy) return
    setBusy(true)
    setActionError(null)
    try {
      await client.cancelTask(activeTaskId)
      jobResource.retry()
      progress.reload()
      taskId.retry()
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '取消失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (!job || busy) return
    if (!window.confirm(`确认删除实验「${job.name || job.id}」？`)) return
    setBusy(true)
    setActionError(null)
    try {
      await client.remove(job.id)
      void navigate('/experiments')
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '删除失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }

  if (!experimentId)
    return <Alert role="alert" type="error" message="缺少实验 ID" />
  if (jobResource.loading) return <Skeleton active paragraph={{ rows: 6 }} />
  if (jobResource.error)
    return (
      <ExperimentFeedback
        message={jobResource.error}
        retry={jobResource.retry}
      />
    )
  if (!job) return <Alert role="alert" type="error" message="实验不存在" />
  const settled = TERMINAL.has(job.status)
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>
            {job.name || job.id} <small>{statusLabel(job.status)}</small>
          </h1>
          <p>
            创建于 {formatDateTime(job.created_at)} · 更新于{' '}
            {formatDateTime(job.updated_at)}
          </p>
        </div>
        <Link className="evaluation-create-link" to="/experiments">
          返回列表
        </Link>
      </header>
      <div className="panel evaluation-panel">
        {actionError && <ExperimentFeedback message={actionError} />}
        {job.error_message && (
          <Alert role="alert" type="error" message={job.error_message} />
        )}
        <ConfigSummary job={job} />
        {ACTIVE.has(job.status) && (
          <div role="status" aria-label="实验进度">
            {progress.task?.progress ? (
              <p>
                {progress.task.progress.current_step || '执行中'} ·{' '}
                {progress.task.progress.current} /{' '}
                {progress.task.progress.total}（
                {progress.task.progress.percentage}%）
              </p>
            ) : (
              <p>等待任务调度…</p>
            )}
            {progress.paused && (
              <Button aria-label="重试进度轮询" onClick={progress.reload}>
                重试进度轮询
              </Button>
            )}
          </div>
        )}
        <div className="evaluation-section-heading">
          {job.status === 'pending' && !activeTaskId && (
            <Button
              type="primary"
              aria-label="启动实验"
              disabled={busy}
              onClick={() => void start()}
            >
              启动实验
            </Button>
          )}
          {activeTaskId && (
            <Button
              aria-label="取消实验"
              disabled={busy}
              onClick={() => void cancel()}
            >
              取消运行
            </Button>
          )}
          <Button danger disabled={busy} onClick={() => void remove()}>
            删除
          </Button>
        </div>
        <Tabs
          items={
            settled
              ? [
                  {
                    key: 'comparison',
                    label: '对比报告',
                    children: <ComparisonTab experimentId={job.id} />,
                  },
                  {
                    key: 'panel',
                    label: '分析面板',
                    children: <PanelTab experimentId={job.id} />,
                  },
                  {
                    key: 'pareto',
                    label: '帕累托',
                    children: <ParetoTab experimentId={job.id} />,
                  },
                  {
                    key: 'optimize',
                    label: '成本建议',
                    children: <OptimizeTab experimentId={job.id} />,
                  },
                ]
              : [
                  {
                    key: 'pending-note',
                    label: '分析',
                    children: (
                      <Alert
                        type="info"
                        message="实验完成后可查看对比报告、帕累托与成本建议。"
                      />
                    ),
                  },
                ]
          }
        />
      </div>
    </section>
  )
}
