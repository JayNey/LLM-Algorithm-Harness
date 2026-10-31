import DatasetPicker from '@/experiments/DatasetPicker.tsx'
import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Input, Select, Skeleton, Tabs } from 'antd'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import type { RunDraftErrors, SuiteDraftErrors } from '@/benchmarks/types.ts'
import { TrendLine } from '@/components/charts/CompareCharts.tsx'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import RunHistory from '@/benchmarks/RunHistory.tsx'
import { historySearch } from '@/benchmarks/history.ts'
import { formatGrowth } from '@/benchmarks/presentation.ts'
import { SuiteForm } from '@/benchmarks/SuiteForm.tsx'
import { useBenchmarkSession } from '@/benchmarks/session.tsx'
import type {
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
import {
  ModelNameField,
  StrategyTagsField,
} from '@/evaluations/optionFields.tsx'
import { useResource } from '@/hooks/useResource.ts'

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

function BenchmarkDetailContent() {
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
  const [search, setSearch] = useSearchParams()
  const committedSearch = useRef(search)
  useLayoutEffect(() => {
    committedSearch.current = search
  }, [search])
  const [historyRevision, setHistoryRevision] = useState(0)
  const submission = useRef(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const loadCurve = useResource(
    useCallback(
      (signal: AbortSignal) => client.learningCurve(suiteId ?? '', signal),
      [client, suiteId],
    ),
  )
  const curve = loadCurve.data as LearningCurve | undefined
  const [metric, setMetric] = useState<'accuracy' | 'cost_usd'>('accuracy')

  async function saveEdit() {
    if (!suite || !editDraft || submission.current) return
    const nextErrors = validateSuiteDraft(editDraft)
    setEditErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    submission.current = true
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
      if (!mounted.current) return
      setEditing(false)
      suiteResource.retry()
      loadCurve.retry()
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '保存失败，请重试',
      )
    } finally {
      submission.current = false
      if (mounted.current) setBusy(false)
    }
  }

  async function launchRun() {
    if (!suite || submission.current) return
    const nextErrors = validateRunDraft(runDraft)
    setRunErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    submission.current = true
    setBusy(true)
    setActionError(null)
    try {
      const startedRun: BenchmarkRunStarted = await client.runSuite(
        suite.id,
        runPayload(runDraft),
      )
      if (!mounted.current) return
      setSearch(
        historySearch(committedSearch.current, { runId: startedRun.id }),
      )
      setHistoryRevision((v) => v + 1)
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '启动失败，请重试',
      )
    } finally {
      submission.current = false
      if (mounted.current) setBusy(false)
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
        <RunHistory
          client={client}
          owner={owner}
          suiteId={suite.id}
          revision={historyRevision}
          onSettled={() => {
            loadCurve.retry()
            setHistoryRevision((v) => v + 1)
          }}
        />
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
                      <small role="alert">{t(runErrors.api_key_id)}</small>
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
                    <ModelNameField
                      ariaLabel={t('基准运行模型')}
                      value={runDraft.model}
                      apiKeyId={runDraft.api_key_id}
                      onChange={(value) =>
                        setRunDraft((previous) => ({
                          ...previous,
                          model: value,
                        }))
                      }
                    />
                    {runErrors.model && (
                      <small role="alert">{t(runErrors.model)}</small>
                    )}
                  </label>
                  <label>
                    {t('策略（逗号分隔，可选）')}
                    <StrategyTagsField
                      ariaLabel={t('基准运行策略')}
                      value={runDraft.strategies_text}
                      onChange={(value) =>
                        setRunDraft((previous) => ({
                          ...previous,
                          strategies_text: value,
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
                      <small role="alert">{t(runErrors.budget_cap_usd)}</small>
                    )}
                  </label>
                  <Button
                    type="primary"
                    aria-label={t('启动基准运行')}
                    disabled={busy}
                    onClick={() => void launchRun()}
                  >
                    {t('启动运行')}
                  </Button>
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
                        onSelectRun={(id) =>
                          setSearch((previous) =>
                            historySearch(previous, { runId: id }),
                          )
                        }
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
                      <ul aria-label={t('曲线运行导航')}>
                        {curve.data
                          .filter((point) => point.run_id)
                          .map((point) => (
                            <li key={point.run_id}>
                              <Link
                                to={{
                                  search: `?${historySearch(search, { runId: point.run_id as string })}`,
                                }}
                              >
                                {point.model} · {point.run_id}
                              </Link>
                            </li>
                          ))}
                      </ul>
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

export default function BenchmarkDetailPage() {
  const { suiteId } = useParams()
  const { owner } = useBenchmarkSession()
  return <BenchmarkDetailContent key={`${owner}:${suiteId}`} />
}
