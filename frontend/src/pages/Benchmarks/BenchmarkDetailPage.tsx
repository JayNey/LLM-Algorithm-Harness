import DatasetPicker from '@/experiments/DatasetPicker.tsx'
import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Input, Select, Skeleton, Tabs } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { RunDraftErrors, SuiteDraftErrors } from '@/benchmarks/types.ts'
import { TrendLine } from '@/components/charts/CompareCharts.tsx'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useTaskProgress } from '@/experiments/useTaskProgress.ts'
import {
  formatDateTime,
  formatGrowth,
  formatRate,
  formatUsd,
  runStatusLabel,
} from '@/benchmarks/presentation.ts'
import { SuiteForm } from '@/benchmarks/SuiteForm.tsx'
import { useBenchmarkSession } from '@/benchmarks/session.tsx'
import type {
  BenchmarkRun,
  BenchmarkRunStarted,
  BenchmarkSuite,
  LearningCurve,
  RunDraft,
  SuiteDraft,
} from '@/benchmarks/types.ts'
import {
  runPayload,
  suiteToDraft,
  validateRunDraft,
  validateSuiteDraft,
} from '@/benchmarks/validation.ts'
import { readApiKeys } from '@/account/apiKeys.ts'
import { useAuthStore } from '@/store/auth.ts'
import type { AxiosInstance } from 'axios'

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

function useApiKeys() {
  const http = useAuthStore.getState().httpClient() as AxiosInstance
  return useResource(
    useCallback(
      async (signal: AbortSignal) => {
        const data = readApiKeys(
          await http.get<unknown, unknown>('/api-keys', {
            signal,
            timeout: 10_000,
          }),
        )
        if (!data) throw new Error('密钥列表响应无效，请重试')
        return data
      },
      [http],
    ),
  )
}

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

export default function BenchmarkDetailPage() {
  useTranslation()

  const { suiteId } = useParams()
  const { client, owner } = useBenchmarkSession()
  const suiteResource = useResource(
    useCallback(
      (signal: AbortSignal) => client.getSuite(suiteId ?? '', signal),
      [client, suiteId],
    ),
  )
  const suite = suiteResource.data as BenchmarkSuite | undefined
  const keys = useApiKeys()

  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState<SuiteDraft | null>(null)
  const [editErrors, setEditErrors] = useState<SuiteDraftErrors>({})
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const [runDraft, setRunDraft] = useState<RunDraft>({
    api_key_id: '',
    dataset_path: '',
    model: '',
    strategies_text: '',
    budget_cap_usd: '',
  })
  const [runErrors, setRunErrors] = useState<RunDraftErrors>({})
  const [started, setStarted] = useState<{
    suiteId: string
    taskId: string
  } | null>(null)

  const activeTaskId =
    started && suite && started.suiteId === suite.id ? started.taskId : null
  const progress = useTaskProgress(client, activeTaskId, owner)
  const taskStatus = progress.task?.status ?? null
  const runFinished = taskStatus !== null && TERMINAL.has(taskStatus)

  const loadCurve = useResource(
    useCallback(
      (signal: AbortSignal) => client.learningCurve(suiteId ?? '', signal),
      // 同上：终态触发学习曲线重取
      [client, suiteId, runFinished],
    ),
  )
  const curve = loadCurve.data as LearningCurve | undefined
  const [metric, setMetric] = useState<'accuracy' | 'cost_usd'>('accuracy')

  const latestRun = useResource(
    useCallback(
      async (signal: AbortSignal): Promise<BenchmarkRun | null> => {
        if (!activeTaskId) return null
        const task = await client.task(activeTaskId, signal)
        return client.run(task.entity_id, signal)
      },
      // runFinished 是刻意加入的重取触发器（任务终态后重取结果）
      [client, activeTaskId, runFinished],
    ),
  )
  const latestRunData = latestRun.data as BenchmarkRun | null | undefined

  async function saveEdit() {
    if (!suite || !editDraft || busy) return
    const nextErrors = validateSuiteDraft(editDraft)
    setEditErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    setActionError(null)
    try {
      await client.updateSuite(suite.id, {
        problems: editDraft.problems_text
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean),
        ...(editDraft.version.trim()
          ? { version: editDraft.version.trim() }
          : {}),
        description: editDraft.description.trim() || null,
        frozen: editDraft.frozen,
      })
      setEditing(false)
      suiteResource.retry()
      loadCurve.retry()
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '保存失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }

  async function launchRun() {
    if (!suite || busy) return
    const nextErrors = validateRunDraft(runDraft)
    setRunErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    setActionError(null)
    try {
      const startedRun: BenchmarkRunStarted = await client.runSuite(
        suite.id,
        runPayload(runDraft),
      )
      setStarted({ suiteId: suite.id, taskId: startedRun.task_id })
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '启动失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }

  if (!suiteId)
    return <Alert role="alert" type="error" message={t('缺少套件 ID')} />
  if (suiteResource.loading) return <Skeleton active paragraph={{ rows: 6 }} />
  if (suiteResource.error)
    return (
      <ExperimentFeedback
        message={t(suiteResource.error)}
        retry={suiteResource.retry}
      />
    )
  if (!suite)
    return <Alert role="alert" type="error" message={t('套件不存在')} />

  const runActive = !!activeTaskId && !progress.paused
  const progressTask = progress.task

  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>
            {suite.name} <small>v{suite.version}</small>
          </h1>
          <p>
            {suite.description ?? t('固定题集基准套件')} ·{' '}
            {suite.problems.length} {t('道题目 · ')}
            {suite.frozen ? t('已冻结') : t('可编辑')}
          </p>
        </div>
        <Link className="evaluation-create-link" to="/benchmarks">
          {t('返回列表')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        {actionError && <ExperimentFeedback message={t(actionError)} />}
        {editing && editDraft && (
          <SuiteForm
            draft={editDraft}
            errors={editErrors}
            disableName
            onChange={(patch) =>
              setEditDraft((previous) => ({
                ...(previous as SuiteDraft),
                ...patch,
              }))
            }
            onSubmit={() => void saveEdit()}
            onCancel={() => setEditing(false)}
            busy={busy}
            submitLabel={t('保存修改')}
          />
        )}
        {!editing && (
          <div className="evaluation-section-heading">
            <Button
              aria-label={t('编辑套件')}
              onClick={() => {
                setEditDraft(suiteToDraft(suite))
                setEditing(true)
              }}
            >
              {t('编辑套件')}
            </Button>
          </div>
        )}
        <Tabs
          items={[
            {
              key: 'run',
              label: t('运行'),
              children: (
                <div>
                  <h3>{t('启动新 run')}</h3>
                  <label>
                    API Key
                    <Select
                      aria-label={t('基准运行密钥')}
                      value={runDraft.api_key_id || undefined}
                      placeholder={t('选择可用密钥')}
                      options={(keys.data ?? []).map((key) => ({
                        value: key.id,
                        label: key.key_name || key.id,
                      }))}
                      onChange={(value: string) =>
                        setRunDraft((previous) => ({
                          ...previous,
                          api_key_id: value,
                        }))
                      }
                    />
                    {runErrors.api_key_id && (
                      <small role="alert">{runErrors.api_key_id}</small>
                    )}
                  </label>
                  <DatasetPicker
                    datasetId={runDraft.dataset_id}
                    datasetPath={runDraft.dataset_path}
                    onChange={(source) =>
                      setRunDraft((previous) => ({ ...previous, ...source }))
                    }
                    disabled={busy}
                    error={runErrors.dataset_path}
                  />
                  <label>
                    {t('模型')}
                    <Input
                      aria-label={t('基准运行模型')}
                      value={runDraft.model}
                      onChange={(event) =>
                        setRunDraft((previous) => ({
                          ...previous,
                          model: event.target.value,
                        }))
                      }
                    />
                    {runErrors.model && (
                      <small role="alert">{runErrors.model}</small>
                    )}
                  </label>
                  <label>
                    {t('策略（逗号分隔，可选）')}
                    <Input
                      aria-label={t('基准运行策略')}
                      value={runDraft.strategies_text}
                      placeholder="vanilla, chain_of_thought"
                      onChange={(event) =>
                        setRunDraft((previous) => ({
                          ...previous,
                          strategies_text: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label>
                    {t('预算上限 USD（可选）')}
                    <Input
                      aria-label={t('基准运行预算')}
                      value={runDraft.budget_cap_usd}
                      onChange={(event) =>
                        setRunDraft((previous) => ({
                          ...previous,
                          budget_cap_usd: event.target.value,
                        }))
                      }
                    />
                    {runErrors.budget_cap_usd && (
                      <small role="alert">{runErrors.budget_cap_usd}</small>
                    )}
                  </label>
                  <Button
                    type="primary"
                    aria-label={t('启动基准运行')}
                    disabled={busy || runActive}
                    onClick={() => void launchRun()}
                  >
                    {runActive ? t('运行中…') : t('启动运行')}
                  </Button>
                  {runActive && progressTask?.progress && (
                    <p role="status">
                      {progressTask.progress.current_step || t('执行中')} ·{' '}
                      {progressTask.progress.current} /{' '}
                      {progressTask.progress.total}（
                      {progressTask.progress.percentage}%）
                    </p>
                  )}
                  {latestRunData && (
                    <table
                      className="evaluation-list-table"
                      aria-label={t('最近一次运行')}
                    >
                      <thead>
                        <tr>
                          {[
                            t('状态 / 错误'),
                            t('模型'),
                            t('准确率'),
                            t('成本'),
                            t('更新时间'),
                          ].map((name) => (
                            <th key={name} scope="col">
                              {name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>
                            {runStatusLabel(latestRunData.status)}
                            <small>
                              {latestRunData.error_message ??
                                progress.task?.error_message ??
                                ''}
                            </small>
                          </td>
                          <td>{latestRunData.model ?? '—'}</td>
                          <td>{formatRate(latestRunData.accuracy)}</td>
                          <td>{formatUsd(latestRunData.cost_usd)}</td>
                          <td>{formatDateTime(latestRunData.updated_at)}</td>
                        </tr>
                      </tbody>
                    </table>
                  )}
                </div>
              ),
            },
            {
              key: 'curve',
              label: t('学习曲线'),
              children: (
                <div>
                  <label>
                    {t('指标')}
                    <Select
                      aria-label={t('学习曲线指标')}
                      value={metric}
                      options={[
                        { value: 'accuracy', label: t('准确率') },
                        { value: 'cost_usd', label: t('成本（USD）') },
                      ]}
                      onChange={(value: 'accuracy' | 'cost_usd') =>
                        setMetric(value)
                      }
                    />
                  </label>
                  {loadCurve.loading ? (
                    <Skeleton active paragraph={{ rows: 5 }} />
                  ) : loadCurve.error ? (
                    <Alert
                      role="alert"
                      type="error"
                      message={t(loadCurve.error)}
                    />
                  ) : curve && curve.data.length ? (
                    <>
                      <TrendLine
                        series={Object.entries(
                          curve.data.reduce<
                            Record<string, LearningCurve['data']>
                          >((groups, point) => {
                            ;(groups[point.model] ??= []).push(point)
                            return groups
                          }, {}),
                        ).map(([model, points]) => ({ model, points }))}
                        metric={metric}
                      />
                      <p role="status">
                        {t('准确率增长：')}
                        {formatGrowth(curve.trends.accuracy_growth_rate)}{' '}
                        {t(' · 成本增长：')}
                        {formatGrowth(curve.trends.cost_growth_rate)}
                      </p>
                    </>
                  ) : (
                    <p role="status">
                      {t(
                        '还没有已完成的 run，启动一次运行后即可看到学习曲线。',
                      )}
                    </p>
                  )}
                </div>
              ),
            },
          ]}
        />
      </div>
    </section>
  )
}
