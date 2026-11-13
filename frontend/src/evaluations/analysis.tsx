import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import {
  Component,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { AutoComplete, Button, Input, Select, Skeleton, Tabs } from 'antd'
import type { AxiosInstance } from 'axios'
import { useAuthStore } from '../store/auth.ts'
import { useResource } from '../hooks/useResource.ts'
import {
  BarCompare,
  RadarChart,
  ScatterPlot,
} from '../components/charts/CompareCharts.tsx'
import {
  createAnalyticsClient,
  type AnalyticsClient,
  type AnalyticsFilters,
  type AnalyticsScope,
  type RateBucket,
  type TokenChart,
} from './analytics.ts'
import { EvaluationFeedback } from './components.tsx'
import {
  metricLabel,
  resultCostLabel,
  successRateLabel,
} from './presentation.ts'
import type { ResultAvailability, StrategySummary } from './types.ts'

type Availability = ResultAvailability['kind']

export interface AnalysisSectionProps {
  scope: AnalyticsScope
  /** 单次运行的结果可用性，用于说明统计范围并在状态变化时重新读取。 */
  availability?: Availability
  /** 当前运行的策略名，作为策略筛选的候选；全账号时留空。 */
  strategyOptions?: readonly string[]
}

const difficulties = ['easy', 'medium', 'hard'] as const

/** 全账号范围由后端限定为已完成运行；单次运行以 run_id 为准。 */
function scopeNote(
  scope: AnalyticsScope,
  filterable: boolean,
  filters: AnalyticsFilters,
): string {
  const base =
    scope.kind === 'run'
      ? t('范围：本次运行')
      : t('范围：全账号 · 仅已完成运行')
  if (!filterable) return `${base} · ${t('不支持筛选')}`
  return `${base} · ${hasFilters(filters) ? t('已应用筛选') : t('未设置筛选')}`
}
function hasFilters(filters: AnalyticsFilters): boolean {
  return Object.values(filters).some((value) => value && value.trim())
}
const availabilityNotes: Partial<Record<Availability, string>> = {
  get waiting() {
    return t('运行尚无已记录结果，分析为空。')
  },
  get partial() {
    return t('以下为当前已记录的部分结果，统计尚非最终结果。')
  },
  get paused() {
    return t('任务已暂停，分析只覆盖已记录的部分结果。')
  },
  get failed() {
    return t('任务失败，分析只覆盖已记录的部分结果。')
  },
  get cancelled() {
    return t('任务已取消，分析只覆盖已记录的部分结果。')
  },
  get incomplete() {
    return t('任务已完成，但记录少于预期单元数，统计不代表完整评估。')
  },
  get empty() {
    return t('任务已完成但没有记录任何单元，分析为空。')
  },
  get unknown() {
    return t('结果未确认，以下统计范围可能不完整。')
  },
}
/** 去掉首尾空白并把空值归一为 undefined：后端精确匹配，且避免 '' 与 undefined 之间的无效重取。 */
// eslint-disable-next-line react-refresh/only-export-components
export function normalizeFilters(filters: AnalyticsFilters): AnalyticsFilters {
  const normalized: AnalyticsFilters = {}
  for (const key of ['strategy', 'difficulty', 'tag'] as const) {
    const value = filters[key]?.trim()
    if (value) normalized[key] = value
  }
  return normalized
}

class PanelBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <EvaluationFeedback
        message={t('面板渲染失败，其他面板不受影响。')}
        retry={() => this.setState({ failed: false })}
      />
    ) : (
      this.props.children
    )
  }
}

interface PanelProps {
  title: string
  note: string
  loading: boolean
  error?: string
  retry: () => void
  empty?: string | false
  children?: ReactNode
}
/** 每个面板独立加载、失败与重试；渲染异常被局部边界隔离。 */
function AnalysisPanel({
  title,
  note,
  loading,
  error,
  retry,
  empty,
  children,
}: PanelProps) {
  useTranslation()

  return (
    <section className="analysis-panel" aria-label={title} aria-busy={loading}>
      <h3>{title}</h3>
      <p className="analysis-scope" role="note">
        {note}
      </p>
      <PanelBoundary>
        {loading ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : error ? (
          <EvaluationFeedback message={t(error)} retry={retry} />
        ) : empty ? (
          <p className="analysis-empty">{empty}</p>
        ) : (
          children
        )}
      </PanelBoundary>
    </section>
  )
}

function Table({
  label,
  head,
  rows,
}: {
  label: string
  head: string[]
  rows: { key: string; cells: ReactNode[] }[]
}) {
  return (
    <div
      className="evaluation-list-scroll analysis-table"
      role="region"
      aria-label={t('可滚动的{{value1}}', { value1: label })}
      tabIndex={0}
    >
      <table className="evaluation-list-table" aria-label={label}>
        <thead>
          <tr>
            {head.map((name) => (
              <th scope="col" key={name}>
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              {row.cells.map((cell, index) => (
                <td key={index}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
function bucketRows(buckets: Record<string, RateBucket>) {
  return Object.entries(buckets).map(([name, row]) => ({
    key: name,
    cells: [
      name,
      `${row.solved} / ${row.total}`,
      successRateLabel(row.success_rate),
    ],
  }))
}
function countRows(counts: Record<string, number>) {
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ key: name, cells: [name, value] }))
}
function strategyRows(strategies: StrategySummary[]) {
  return strategies.map((strategy) => ({
    key: strategy.name,
    cells: [
      strategy.name,
      `${strategy.solved_problems} / ${strategy.total_problems}`,
      successRateLabel(strategy.success_rate),
      metricLabel(strategy.avg_tokens),
      metricLabel(strategy.avg_execution_time, t('秒')),
      resultCostLabel(strategy),
    ],
  }))
}
const strategyHead = () => [
  t('策略'),
  t('成功 / 已评估单元'),
  t('成功率'),
  t('平均 Token'),
  t('平均执行耗时'),
  t('估算费用'),
]
const percent = (value: number) => Number((value * 100).toFixed(2))

interface Scoped {
  client: AnalyticsClient
  scope: AnalyticsScope
  filters: AnalyticsFilters
}
type Reader<T> = (
  client: AnalyticsClient,
  scope: AnalyticsScope,
  filters: AnalyticsFilters,
  signal: AbortSignal,
) => Promise<T>
const runIdOf = (scope: AnalyticsScope) =>
  scope.kind === 'run' ? scope.runId : ''
const reader = <T,>(fn: Reader<T>) => fn
// 模块级读取器保持引用稳定，load 身份只随 client / 范围 / 筛选 / 纪元变化。
const readers = {
  successRate: reader((c, s, f, signal) => c.successRate(s, f, signal)),
  tokens: reader((c, s, f, signal) => c.tokens(s, f, signal)),
  iterations: reader((c, s, f, signal) => c.iterations(s, f, signal)),
  failureModes: reader((c, s, f, signal) => c.failureModes(s, f, signal)),
  successRateChart: reader((c, s, f, signal) =>
    c.successRateChart(s, f, signal),
  ),
  tokenChart: reader((c, s, f, signal) => c.tokenChart(s, f, signal)),
  costAccuracy: reader((c, s, f, signal) => c.costAccuracy(s, f, signal)),
  capabilityRadar: reader((c, s, f, signal) => c.capabilityRadar(s, f, signal)),
  failuresByTag: reader((c, s, f, signal) => c.failuresByTag(s, f, signal)),
  failureSummary: reader((c, s, _f, signal) =>
    c.failureSummary(runIdOf(s), signal),
  ),
  failureCases: reader((c, s, _f, signal) =>
    c.failureCases(runIdOf(s), signal),
  ),
  compareStrategies: reader((c, s, _f, signal) =>
    c.compareStrategies(runIdOf(s), signal),
  ),
  compareModels: reader((c, _s, _f, signal) => c.compareModels(signal)),
  compareHistory: reader((c, s, _f, signal) =>
    c.compareHistory(runIdOf(s), signal),
  ),
}
/** filterable 面板的 load 身份包含筛选；其余面板只随运行/账号变化。 */
function useScopedLoad<T>(
  { client, scope, filters }: Scoped,
  filterable: boolean,
  read: Reader<T>,
) {
  // 不支持筛选的面板把筛选值固定为 undefined，筛选变化不得改变其 load 身份。
  const strategy = filterable ? filters.strategy : undefined
  const difficulty = filterable ? filters.difficulty : undefined
  const tag = filterable ? filters.tag : undefined
  const applied = useMemo<AnalyticsFilters>(
    () => ({ strategy, difficulty, tag }),
    [strategy, difficulty, tag],
  )
  const runId = scope.kind === 'run' ? scope.runId : null
  const load = useCallback(
    (signal: AbortSignal) =>
      read(
        client,
        runId === null ? { kind: 'account' } : { kind: 'run', runId },
        applied,
        signal,
      ),
    [client, runId, applied, read],
  )
  return useResource(load)
}

function SuccessRatePanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.successRate)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('成功率统计')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.total === 0 && t('当前范围没有匹配的单元。')}
    >
      {data && (
        <>
          <p>
            {t(
              '成功 {{value1}} / {{value2}}（{{value3}}）· 平均执行耗时 {{value4}}',
              {
                value1: data.solved,
                value2: data.total,
                value3: successRateLabel(data.success_rate),
                value4: metricLabel(data.avg_execution_time, t('秒')),
              },
            )}
          </p>
          <h4>{t('按难度')}</h4>
          {Object.keys(data.by_difficulty).length ? (
            <Table
              label={t('按难度成功率')}
              head={[t('难度'), t('成功 / 已评估单元'), t('成功率')]}
              rows={bucketRows(data.by_difficulty)}
            />
          ) : (
            <p className="analysis-empty">{t('没有可归类难度的单元。')}</p>
          )}
          <h4>{t('按标签')}</h4>
          {Object.keys(data.by_tag).length ? (
            <Table
              label={t('按标签成功率')}
              head={[t('标签'), t('成功 / 已评估单元'), t('成功率')]}
              rows={bucketRows(data.by_tag)}
            />
          ) : (
            <p className="analysis-empty">
              {t('没有带标签的单元：执行快照标签为空的单元不计入标签统计。')}
            </p>
          )}
        </>
      )}
    </AnalysisPanel>
  )
}

function TokensPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.tokens)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('Token 与费用')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
    >
      {data && (
        <dl className="evaluation-facts analysis-facts">
          <div>
            <dt>{t('Token 合计')}</dt>
            <dd>{metricLabel(data.total_tokens)}</dd>
          </div>
          <div>
            <dt>{t('平均 Token')}</dt>
            <dd>{metricLabel(data.avg_tokens)}</dd>
          </div>
          <div>
            <dt>{t('估算费用')}</dt>
            <dd>{resultCostLabel(data)}</dd>
          </div>
          <div>
            <dt>{t('未知费用条数')}</dt>
            <dd>{data.unknown_cost_count}</dd>
          </div>
        </dl>
      )}
      {data && data.unknown_cost_count > 0 && (
        <p role="note">
          {t('存在缺少定价或用量的单元，已知费用是下限而不是精确总额。')}
        </p>
      )}
    </AnalysisPanel>
  )
}

function IterationsPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.iterations)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('迭代次数')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={
        data?.known_count === 0 &&
        data.unknown_count === 0 &&
        t('当前范围没有匹配的单元。')
      }
    >
      {data && (
        <>
          <p>
            {t(
              '已记录迭代 {{value1}} 条，未记录 {{value2}} 条；平均 {{value3}}',
              {
                value1: data.known_count,
                value2: data.unknown_count,
                value3: metricLabel(data.average),
              },
            )}
          </p>
          {data.distribution.length > 0 && (
            <Table
              label={t('迭代分布')}
              head={[t('迭代次数'), t('单元数')]}
              rows={data.distribution.map((row) => ({
                key: String(row.iterations),
                cells: [row.iterations, row.count],
              }))}
            />
          )}
        </>
      )}
    </AnalysisPanel>
  )
}

function FailureModesPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.failureModes)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('失败模式')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data && Object.keys(data).length === 0 && t('没有失败单元。')}
    >
      {data && (
        <Table
          label={t('失败模式')}
          head={[t('失败模式'), t('单元数')]}
          rows={countRows(data)}
        />
      )}
    </AnalysisPanel>
  )
}

function SuccessRateChartPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.successRateChart)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('各策略成功率')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.points.length === 0 && t('当前范围没有匹配的单元。')}
    >
      {data && (
        <>
          <BarCompare
            labels={data.points.map((point) => point.name)}
            series={[
              {
                name: t('成功率（%）'),
                values: data.points.map((point) => percent(point.success_rate)),
              },
            ]}
            yName={t('成功率（%）')}
          />
          <Table
            label={t('各策略成功率')}
            head={[t('策略'), t('成功率')]}
            rows={data.points.map((point) => ({
              key: point.name,
              cells: [point.name, successRateLabel(point.success_rate)],
            }))}
          />
        </>
      )}
    </AnalysisPanel>
  )
}

export interface TokenChartView {
  labels: string[]
  series: { name: string; values: (number | null)[] }[]
}
/** 全账号范围同一题目会按多次运行重复出现在同一策略序列里：按出现次序各占一个类目，不丢弃任何单元。 */
// eslint-disable-next-line react-refresh/only-export-components
export function tokenChartView(series: TokenChart['series']): TokenChartView {
  // 类目以 (出现次序, 题目 ID) 为内部键，展示标签单独生成：真实题目 ID 形如 "x #2" 时也不会与生成标签合并。
  const keys: string[] = []
  const labels: string[] = []
  const keyIndex = new Set<string>()
  const perSeries = series.map((group) => {
    const ordinal = new Map<string, number>()
    const values = new Map<string, number | null>()
    for (const point of group.points) {
      const occurrence = (ordinal.get(point.problem_id) ?? 0) + 1
      ordinal.set(point.problem_id, occurrence)
      const key = `${occurrence}\u0000${point.problem_id}`
      if (!keyIndex.has(key)) {
        keyIndex.add(key)
        keys.push(key)
        labels.push(
          occurrence === 1
            ? point.problem_id
            : `${point.problem_id} #${occurrence}`,
        )
      }
      values.set(key, point.tokens)
    }
    return { name: group.name, values }
  })
  return {
    labels,
    series: perSeries.map((item) => ({
      name: item.name,
      values: keys.map((key) => item.values.get(key) ?? null),
    })),
  }
}

function TokenChartPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.tokenChart)
  const data = state.data
  const chart = useMemo(
    () => (data ? tokenChartView(data.series) : null),
    [data],
  )
  return (
    <AnalysisPanel
      title={t('逐题 Token')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={chart?.labels.length === 0 && t('当前范围没有匹配的单元。')}
    >
      {data && chart && (
        <>
          <BarCompare labels={chart.labels} series={chart.series} zoom />
          <Table
            label={t('逐题 Token 概览')}
            head={[t('策略'), t('单元数'), t('缺少 Token 记录的单元')]}
            rows={data.series.map((group) => ({
              key: group.name,
              cells: [
                group.name,
                group.points.length,
                group.points.filter((point) => point.tokens === null).length,
              ],
            }))}
          />
        </>
      )}
    </AnalysisPanel>
  )
}

function CostAccuracyPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.costAccuracy)
  // 散点本身不带未知费用数，用同筛选的 tokens 统计如实标注。
  const tokens = useScopedLoad(props, true, readers.tokens)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('成本与准确率')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.points.length === 0 && t('当前范围没有匹配的单元。')}
    >
      {data && (
        <>
          <ScatterPlot
            points={data.points.map((point) => ({
              label: point.name,
              x: point.estimated_cost_usd,
              y: percent(point.success_rate),
            }))}
            xName={t('已知估算费用（USD）')}
            yName={t('成功率（%）')}
          />
          {tokens.loading ? (
            <p role="status">{t('正在核对未知费用条数…')}</p>
          ) : tokens.error ? (
            <EvaluationFeedback
              message={t('{{value1}}；无法确认未知费用条数。', {
                value1: t(tokens.error),
              })}
              retry={tokens.retry}
            />
          ) : tokens.data && tokens.data.unknown_cost_count > 0 ? (
            <p role="note">
              {t(
                '统计含 {{value1}} 条成本未知单元；横轴只计已知费用，是下限而不是精确总额。',
                {
                  value1: tokens.data.unknown_cost_count,
                },
              )}
            </p>
          ) : (
            <p role="note">{t('所有单元费用已知。')}</p>
          )}
          <Table
            label={t('成本与准确率')}
            head={[t('策略'), t('成功率'), t('已知估算费用')]}
            rows={data.points.map((point) => ({
              key: point.name,
              cells: [
                point.name,
                successRateLabel(point.success_rate),
                metricLabel(point.estimated_cost_usd, 'USD'),
              ],
            }))}
          />
        </>
      )}
    </AnalysisPanel>
  )
}

function RadarPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.capabilityRadar)
  const data = state.data
  const unnamed = t('未标注模型')
  return (
    <AnalysisPanel
      title={t('能力雷达')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.series.length === 0 && t('当前范围没有匹配的单元。')}
    >
      {data && (
        <>
          <RadarChart
            labels={data.dimensions}
            datasets={data.series.map((group) => ({
              label: group.name ?? unnamed,
              values: group.data,
            }))}
            max={100}
          />
          <p role="note">
            {t(
              '维度得分为后端按执行快照标签计算的 0–100 成功率；没有可映射标签的题目不计入任何维度。',
            )}
          </p>
          <Table
            label={t('能力雷达')}
            head={[
              t('维度'),
              t('题目数'),
              ...data.series.map((group) => group.name ?? unnamed),
            ]}
            rows={data.dimensions.map((dimension, index) => ({
              key: dimension,
              cells: [
                dimension,
                data.problem_counts[dimension] ?? 0,
                ...data.series.map((group) => group.data[index] ?? 0),
              ],
            }))}
          />
        </>
      )}
    </AnalysisPanel>
  )
}

function FailuresByTagPanel(props: Scoped) {
  const state = useScopedLoad(props, true, readers.failuresByTag)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('按标签成功率')}
      note={scopeNote(props.scope, true, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={
        data &&
        Object.keys(data.tags).length === 0 &&
        t('没有带标签的单元：执行快照标签为空的单元不计入标签统计。')
      }
    >
      {data && (
        <Table
          label={t('按标签成功率')}
          head={[t('标签'), t('成功 / 已评估单元'), t('成功率')]}
          rows={bucketRows(data.tags)}
        />
      )}
    </AnalysisPanel>
  )
}

function FailureSummaryPanel(props: Scoped) {
  const state = useScopedLoad(props, false, readers.failureSummary)
  const data = state.data
  const empty =
    !!data &&
    !Object.keys(data.modes).length &&
    !Object.keys(data.categories).length &&
    !data.clusters.length
  return (
    <AnalysisPanel
      title={t('失败摘要')}
      note={scopeNote(props.scope, false, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={empty && t('本次运行没有失败单元。')}
    >
      {data && (
        <>
          <h4>{t('失败模式')}</h4>
          {Object.keys(data.modes).length ? (
            <Table
              label={t('失败模式')}
              head={[t('失败模式'), t('单元数')]}
              rows={countRows(data.modes)}
            />
          ) : (
            <p className="analysis-empty">{t('没有记录失败模式。')}</p>
          )}
          <h4>{t('失败分类')}</h4>
          {Object.keys(data.categories).length ? (
            <Table
              label={t('失败分类')}
              head={[t('失败分类'), t('单元数')]}
              rows={countRows(data.categories)}
            />
          ) : (
            <p className="analysis-empty">{t('没有记录失败分类。')}</p>
          )}
          <h4>{t('错误聚类')}</h4>
          {data.clusters.length ? (
            <Table
              label={t('错误聚类')}
              head={[t('归一化错误模式'), t('单元数')]}
              rows={data.clusters.map((row, index) => ({
                key: `${index}:${row.pattern}`,
                cells: [row.pattern || t('（空）'), row.count],
              }))}
            />
          ) : (
            <p className="analysis-empty">
              {t('没有可聚类的错误信息（失败单元未记录错误信息）。')}
            </p>
          )}
        </>
      )}
    </AnalysisPanel>
  )
}

function FailureCasesPanel(props: Scoped) {
  const state = useScopedLoad(props, false, readers.failureCases)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('失败案例')}
      note={scopeNote(props.scope, false, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.items.length === 0 && t('本次运行没有失败单元。')}
    >
      {data && (
        <>
          <p>
            {t('共 {{value1}} 条非成功单元。', { value1: data.items.length })}
          </p>
          <Table
            label={t('失败案例')}
            head={[t('题目 ID'), t('策略'), t('单元状态'), t('错误信息')]}
            rows={data.items.map((row, index) => ({
              key: `${index}:${row.problem_id}:${row.strategy}`,
              cells: [
                row.problem_id,
                row.strategy,
                row.status,
                row.error_message === null ? t('未记录') : row.error_message,
              ],
            }))}
          />
        </>
      )}
    </AnalysisPanel>
  )
}

function CompareStrategiesPanel(props: Scoped) {
  const state = useScopedLoad(props, false, readers.compareStrategies)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('策略对比')}
      note={scopeNote(props.scope, false, props.filters)}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.strategies.length === 0 && t('本次运行尚无策略统计。')}
    >
      {data && (
        <>
          <BarCompare
            labels={data.strategies.map((strategy) => strategy.name)}
            series={[
              {
                name: t('成功率（%）'),
                values: data.strategies.map((strategy) =>
                  percent(strategy.success_rate),
                ),
              },
            ]}
            yName={t('成功率（%）')}
          />
          <Table
            label={t('策略对比')}
            head={strategyHead()}
            rows={strategyRows(data.strategies)}
          />
        </>
      )}
    </AnalysisPanel>
  )
}

function CompareHistoryPanel(props: Scoped) {
  const state = useScopedLoad(props, false, readers.compareHistory)
  const data = state.data
  return (
    <AnalysisPanel
      title={t('历史对比')}
      note={`${t('范围：与本次运行同模型且策略集合相同的其他运行')} · ${t('不支持筛选')}`}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={
        data?.series.length === 0 && t('没有同模型且策略集合相同的历史运行。')
      }
    >
      {data && (
        <Table
          label={t('历史对比')}
          head={[t('运行记录'), t('完成时间'), t('各策略成功率')]}
          rows={data.series.map((run, index) => ({
            key: `${index}:${run.run_id ?? ''}`,
            cells: [
              run.run_id ?? t('未关联'),
              run.completed_at ?? t('未完成'),
              run.strategies.length
                ? run.strategies.map((strategy) => (
                    <div key={strategy.name}>
                      {strategy.name}：{successRateLabel(strategy.success_rate)}
                      （{strategy.solved_problems} / {strategy.total_problems}）
                    </div>
                  ))
                : t('尚无策略统计'),
            ],
          }))}
        />
      )}
    </AnalysisPanel>
  )
}

function CompareModelsPanel(props: Scoped) {
  const state = useScopedLoad(props, false, readers.compareModels)
  const data = state.data
  const unnamed = t('未标注模型')
  return (
    <AnalysisPanel
      title={t('模型对比')}
      note={`${t('范围：全账号 · 仅已完成运行')} · ${t('不支持筛选')}`}
      loading={state.loading}
      error={state.error}
      retry={state.retry}
      empty={data?.models.length === 0 && t('账号下没有已完成的运行。')}
    >
      {data && (
        <Table
          label={t('模型对比')}
          head={[t('模型'), ...strategyHead()]}
          rows={data.models.flatMap((group) =>
            group.strategies.length
              ? strategyRows(group.strategies).map((row) => ({
                  key: `${group.model ?? ''}:${row.key}`,
                  cells: [group.model ?? unnamed, ...row.cells],
                }))
              : [
                  {
                    key: `${group.model ?? ''}:`,
                    cells: [
                      group.model ?? unnamed,
                      t('尚无策略统计'),
                      '',
                      '',
                      '',
                      '',
                      '',
                    ],
                  },
                ],
          )}
        />
      )}
    </AnalysisPanel>
  )
}

function FilterBar({
  filters,
  strategyOptions,
  onApply,
}: {
  filters: AnalyticsFilters
  strategyOptions: readonly string[]
  onApply: (filters: AnalyticsFilters) => void
}) {
  useTranslation()

  const [draft, setDraft] = useState<AnalyticsFilters>(filters)
  return (
    <form
      className="analysis-filters"
      aria-label={t('分析筛选')}
      onSubmit={(event) => {
        event.preventDefault()
        onApply(draft)
      }}
    >
      <label>
        <span>{t('策略')}</span>
        <AutoComplete
          aria-label={t('策略筛选')}
          allowClear
          value={draft.strategy ?? ''}
          options={strategyOptions.map((name) => ({ value: name }))}
          onChange={(value) =>
            setDraft((current) => ({ ...current, strategy: value ?? '' }))
          }
          placeholder={t('全部策略')}
        />
      </label>
      <label>
        <span>{t('难度')}</span>
        <Select
          aria-label={t('难度筛选')}
          allowClear
          value={draft.difficulty || undefined}
          options={difficulties.map((value) => ({ value, label: value }))}
          onChange={(value: string | undefined) =>
            setDraft((current) => ({ ...current, difficulty: value ?? '' }))
          }
          placeholder={t('全部难度')}
        />
      </label>
      <label>
        <span>{t('标签')}</span>
        <Input
          aria-label={t('标签筛选')}
          allowClear
          value={draft.tag ?? ''}
          onChange={(event) =>
            setDraft((current) => ({ ...current, tag: event.target.value }))
          }
          placeholder={t('单个标签，精确且区分大小写')}
        />
      </label>
      <div className="evaluation-actions analysis-filter-actions">
        <Button type="primary" htmlType="submit">
          {t('应用筛选')}
        </Button>
        <Button
          onClick={() => {
            setDraft({})
            onApply({})
          }}
          disabled={!hasFilters(draft) && !hasFilters(filters)}
        >
          {t('清除筛选')}
        </Button>
        <span>{t('筛选只作用于标注"已应用筛选"的面板。')}</span>
      </div>
    </form>
  )
}

/** 结果分析分区：按 scope 组织统计 / 图表 / 失败分析 / 对比，惰性挂载各分区。 */
export function AnalysisSection({
  scope,
  availability,
  strategyOptions = [],
}: AnalysisSectionProps) {
  useTranslation()

  const client = useMemo(
    () =>
      createAnalyticsClient(
        useAuthStore.getState().httpClient() as AxiosInstance,
      ),
    [],
  )
  const [filters, setFilters] = useState<AnalyticsFilters>({})
  const scoped: Scoped = { client, scope, filters }
  // 可用性纪元：结果状态变化或用户点击刷新时整组面板重挂并重新读取；翻页不改变它。
  const [refreshCount, setRefreshCount] = useState(0)
  const epoch = `${availability ?? ''}:${refreshCount}`
  const runId = scope.kind === 'run' ? scope.runId : null
  const note = availability ? availabilityNotes[availability] : undefined
  const items = [
    {
      key: 'stats',
      label: t('统计'),
      children: (
        <div className="analysis-grid" key={epoch}>
          <SuccessRatePanel {...scoped} />
          <TokensPanel {...scoped} />
          <IterationsPanel {...scoped} />
          <FailureModesPanel {...scoped} />
        </div>
      ),
    },
    {
      key: 'charts',
      label: t('图表'),
      children: (
        <div className="analysis-grid" key={epoch}>
          <SuccessRateChartPanel {...scoped} />
          <TokenChartPanel {...scoped} />
          <CostAccuracyPanel {...scoped} />
          <RadarPanel {...scoped} />
        </div>
      ),
    },
    {
      key: 'failures',
      label: runId === null ? t('按标签成功率') : t('失败分析'),
      children: (
        <div className="analysis-grid" key={epoch}>
          <FailuresByTagPanel {...scoped} />
          {runId !== null && (
            <>
              <FailureSummaryPanel {...scoped} />
              <FailureCasesPanel {...scoped} />
            </>
          )}
        </div>
      ),
    },
    {
      key: 'compare',
      label: runId === null ? t('模型对比') : t('对比'),
      children: (
        <div className="analysis-grid" key={epoch}>
          {runId === null ? (
            <CompareModelsPanel {...scoped} />
          ) : (
            <>
              <CompareStrategiesPanel {...scoped} />
              <CompareHistoryPanel {...scoped} />
            </>
          )}
        </div>
      ),
    },
  ]
  return (
    <div className="analysis-section">
      <p role="status" className="analysis-scope">
        {runId === null
          ? t('全账号统计只包含已完成的运行，不会按当前任务筛选。')
          : t(
              '以下统计以运行记录 {{value1}} 为范围，由服务端全量聚合，不随单题分页变化。',
              {
                value1: runId,
              },
            )}
        {note ? ` ${note}` : ''}
      </p>
      <div className="evaluation-actions analysis-section-actions">
        <Button onClick={() => setRefreshCount((value) => value + 1)}>
          {t('刷新分析')}
        </Button>
        {runId !== null && (
          <span>{t('运行中的结果不会自动刷新分析面板，需要时手动刷新。')}</span>
        )}
      </div>
      <FilterBar
        filters={filters}
        strategyOptions={strategyOptions}
        onApply={(next) => setFilters(normalizeFilters(next))}
      />
      <Tabs items={items} />
    </div>
  )
}

/** run_id 缺失时不发任何分析请求，与报告下载保持相同口径。 */
export function AnalysisUnavailable() {
  useTranslation()
  return (
    <p className="analysis-empty">
      {t('运行记录未关联，暂不可分析；不会以评估 ID 代替运行记录发起请求。')}
    </p>
  )
}
