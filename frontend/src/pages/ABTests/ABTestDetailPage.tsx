import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Skeleton, Tabs } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import {
  formatDateTime,
  formatDiff,
  formatRate,
  statusLabel,
  testMethodLabel,
} from '@/abtests/presentation.ts'
import { useABTestSession } from '@/abtests/session.tsx'
import type { ABTestJob, ABTestResults } from '@/abtests/types.ts'
import { useStatusPolling } from '@/abtests/useStatusPolling.ts'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

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

function ResultsTab({ testId }: { testId: string }) {
  useTranslation()

  const { client } = useABTestSession()
  const results = useResource(
    useCallback(
      (signal: AbortSignal) => client.results(testId, signal),
      [client, testId],
    ),
  )
  if (results.loading) return <Skeleton active paragraph={{ rows: 5 }} />
  if (results.error)
    return <Alert role="alert" type="error" message={t(results.error)} />
  const data = results.data as ABTestResults
  const rows = [
    { name: t('样本通过率'), pair: data.comparison.sample },
    { name: t('正式通过率'), pair: data.comparison.formal },
  ]
  return (
    <div>
      <h3>{t('通过率对比（基线 vs 实验组）')}</h3>
      <table className="evaluation-list-table" aria-label={t('A/B 通过率对比')}>
        <thead>
          <tr>
            {[
              t('口径'),
              t('基线'),
              t('实验组'),
              t('差值'),
              t('95% 置信区间'),
            ].map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ name, pair }) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{formatRate(pair.baseline)}</td>
              <td>{formatRate(pair.treatment)}</td>
              <td>{formatDiff(pair.ci95.difference)}</td>
              <td>
                {pair.ci95.lower === null || pair.ci95.upper === null
                  ? '—'
                  : `[${formatDiff(pair.ci95.lower)}, ${formatDiff(pair.ci95.upper)}]`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>{t('统计检验')}</h3>
      <p>
        {t('方法：')}
        {testMethodLabel(data.comparison.statistics.categorical_test)}{' '}
        {t(' · p 值：')}
        {data.comparison.statistics.p_value === null
          ? '—'
          : data.comparison.statistics.p_value}{' '}
        {t('· Welch t p 值：')}
        {data.comparison.statistics.welch_t_p_value === null
          ? '—'
          : data.comparison.statistics.welch_t_p_value}
      </p>
      <h3>{t('按变体统计')}</h3>
      {Object.keys(data.comparison.elapsed_seconds).length ||
      Object.keys(data.comparison.failure_categories).length ? (
        <table className="evaluation-list-table" aria-label={t('按变体统计')}>
          <thead>
            <tr>
              {[t('变体'), t('总耗时（秒）'), t('token 数'), t('失败分类')].map(
                (name) => (
                  <th key={name} scope="col">
                    {name}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {Object.keys(data.comparison.elapsed_seconds)
              .concat(Object.keys(data.comparison.failure_categories))
              .filter((variant, index, all) => all.indexOf(variant) === index)
              .map((variant) => {
                const categories =
                  data.comparison.failure_categories[variant] ?? {}
                const summary = Object.keys(categories).length
                  ? Object.entries(categories)
                      .map(
                        ([category, countValue]) => `${category}×${countValue}`,
                      )
                      .join('、')
                  : t('无失败')
                return (
                  <tr key={variant}>
                    <td>{variant}</td>
                    <td>
                      {data.comparison.elapsed_seconds[variant] !== undefined
                        ? data.comparison.elapsed_seconds[variant].toFixed(1)
                        : '—'}
                    </td>
                    <td>{data.comparison.tokens[variant] ?? '—'}</td>
                    <td>{summary}</td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      ) : (
        <p>{t('无失败记录')}</p>
      )}
    </div>
  )
}

export default function ABTestDetailPage() {
  useTranslation()

  const { testId } = useParams()
  const { client } = useABTestSession()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const initial = useResource(
    useCallback(
      (signal: AbortSignal) => client.get(testId ?? '', signal),
      [client, testId],
    ),
  )
  const status = useStatusPolling(client, testId ?? null)
  const job: ABTestJob | undefined = status.job ?? initial.data

  async function launch() {
    if (!testId || busy) return
    setBusy(true)
    setActionError(null)
    try {
      await client.run(testId)
      status.reload()
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '启动失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (!testId || busy) return
    if (!window.confirm(t('确认删除该 A/B 测试？'))) return
    setBusy(true)
    setActionError(null)
    try {
      await client.remove(testId)
      void navigate('/ab-tests')
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '删除失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }

  if (!testId)
    return <Alert role="alert" type="error" message={t('缺少测试 ID')} />
  if (initial.loading && !job)
    return <Skeleton active paragraph={{ rows: 6 }} />
  if (initial.error && !job)
    return (
      <ExperimentFeedback message={t(initial.error)} retry={initial.retry} />
    )
  if (!job) return <Alert role="alert" type="error" message={t('测试不存在')} />
  const settled = TERMINAL.has(job.status)
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>
            {job.name || job.id} <small>{statusLabel(job.status)}</small>
          </h1>
          <p>
            {t('创建于 ')}
            {formatDateTime(job.created_at)} {t(' · 更新于')}{' '}
            {formatDateTime(job.updated_at)}
          </p>
        </div>
        <Link className="evaluation-create-link" to="/ab-tests">
          {t('返回列表')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        {actionError && <ExperimentFeedback message={t(actionError)} />}
        {job.error_message && (
          <Alert role="alert" type="error" message={job.error_message} />
        )}
        <dl>
          <dt>{t('数据集')}</dt>
          <dd>{job.config.dataset_path}</dd>
          <dt>{t('模型 / 策略')}</dt>
          <dd>
            {job.config.model.model} × {job.config.strategy.name}（seed{' '}
            {job.config.seed}）
          </dd>
          <dt>{t('变体')}</dt>
          <dd>
            {job.config.prompt_variants
              .map((variant) => variant.id)
              .join(' / ')}
          </dd>
        </dl>
        <div className="evaluation-section-heading">
          {job.status === 'pending' && !job.task_id && (
            <Button
              type="primary"
              aria-label={t('启动 A/B 测试')}
              disabled={busy}
              onClick={() => void launch()}
            >
              {t('启动测试')}
            </Button>
          )}
          {job.status === 'pending' && job.task_id && (
            <span role="status">{t('测试已排队，等待开始执行…')}</span>
          )}
          {job.status === 'running' && (
            <span role="status">{t('测试执行中，完成后自动展示结果…')}</span>
          )}
          <Button
            danger
            disabled={
              busy ||
              Boolean(
                job.task_id &&
                ['pending', 'running', 'paused'].includes(job.status),
              )
            }
            onClick={() => void remove()}
          >
            {t('删除')}
          </Button>
        </div>
        <Tabs
          items={
            settled
              ? [
                  {
                    key: 'results',
                    label: t('结果统计'),
                    children:
                      job.status === 'completed' ? (
                        <ResultsTab testId={job.id} />
                      ) : (
                        <Alert
                          role="alert"
                          type="error"
                          message={job.error_message ?? t('测试未产出结果')}
                        />
                      ),
                  },
                ]
              : [
                  {
                    key: 'pending-note',
                    label: t('结果'),
                    children: (
                      <Alert
                        type="info"
                        message={t(
                          '测试完成后可查看通过率对比与统计检验结果。',
                        )}
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
