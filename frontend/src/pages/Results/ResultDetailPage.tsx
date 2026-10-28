import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button } from 'antd'
import { useCallback, useEffect, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  EvaluationFacts,
  EvaluationFeedback,
  ResultTables,
} from '@/evaluations/components.tsx'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import {
  useEvaluation,
  useEvaluationLive,
  isLiveStatus,
} from '@/evaluations/useEvaluation.ts'
import { fetchEvaluationResult } from '@/evaluations/results.ts'
import { readListQuery, writeListQuery } from '@/evaluations/validation.ts'
import {
  resultAvailability,
  resultStatusLabel,
} from '@/evaluations/presentation.ts'
import type { ResultAvailability } from '@/evaluations/types.ts'
import { useAuthStore } from '@/store/auth.ts'
import '@/evaluations/workflow.css'

const availabilityLabels: Record<ResultAvailability['kind'], string> = {
  get waiting() {
    return t('等待结果')
  },
  get partial() {
    return t('运行中部分结果')
  },
  get paused() {
    return t('任务已暂停')
  },
  get failed() {
    return t('任务失败')
  },
  get cancelled() {
    return t('任务已取消')
  },
  get complete() {
    return t('结果完整')
  },
  get incomplete() {
    return t('结果不完整')
  },
  get empty() {
    return t('已完成，无结果')
  },
  get unknown() {
    return t('结果未确认')
  },
}

export default function ResultDetailPage() {
  useTranslation()

  const { evaluationId = '' } = useParams()
  const { client, owner } = useEvaluationSession()
  const [search, setSearch] = useSearchParams()
  const rawSearch = search.toString()
  const page = useMemo(() => {
    const { limit, offset } = readListQuery(new URLSearchParams(rawSearch))
    return { limit, offset }
  }, [rawSearch])
  const load = useCallback(
    (id: string, signal: AbortSignal) =>
      fetchEvaluationResult(client, id, page, signal),
    [client, page],
  )
  const bootstrap = useEvaluation(client, evaluationId, owner, load)
  const liveEnabled = !!bootstrap.data && isLiveStatus(bootstrap.data.status)
  const live = useEvaluationLive(
    client,
    evaluationId,
    owner,
    liveEnabled,
    load,
    bootstrap.discard,
  )
  const current =
    live.forbidden || live.unauthorized
      ? undefined
      : (live.evaluation ?? bootstrap.data)
  const error = live.forbidden
    ? t('任务不可访问，请刷新后重试')
    : (live.error ?? bootstrap.error)
  const result = current?.result
  const availability = current ? resultAvailability(current, result) : undefined
  const outOfRange =
    !!result && page.offset > 0 && page.offset >= result.problems.total
  const clear = useAuthStore((state) => state.clear)
  useEffect(() => {
    if (live.unauthorized) clear()
  }, [live.unauthorized, clear])
  useEffect(() => {
    const next = writeListQuery(
      outOfRange && result
        ? {
            ...page,
            offset:
              Math.floor(Math.max(0, result.problems.total - 1) / page.limit) *
              page.limit,
          }
        : page,
    )
    if (next.toString() !== rawSearch) setSearch(next, { replace: true })
  }, [page, rawSearch, setSearch, result, outOfRange])
  const { refresh: refreshLive } = live
  const { reload } = bootstrap
  const refresh = useCallback(() => {
    if (liveEnabled) refreshLive()
    else reload()
  }, [liveEnabled, refreshLive, reload])
  const loading = bootstrap.loading || outOfRange
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('评估结果详情')}</h1>
          <p>{t('查看任务事实、全量策略统计与已记录的单题结果。')}</p>
        </div>
        <Link to="/results">{t('返回结果列表')}</Link>
      </header>
      <section
        className="panel evaluation-panel"
        aria-label={t('任务信息')}
        aria-busy={loading}
      >
        <dl className="evaluation-receipt">
          <dt>{t('评估 ID')}</dt>
          <dd>{evaluationId}</dd>
        </dl>
        {loading && <p role="status">{t('正在加载评估结果…')}</p>}
        {error && (
          <EvaluationFeedback
            message={t(
              current
                ? t('{{value1}}；下方为上次读取的数据。', { value1: t(error) })
                : error,
            )}
            retry={refresh}
          />
        )}
        {current && <EvaluationFacts evaluation={current} />}
        {live.mode === 'live' && <p role="status">{t('实时进度已连接')}</p>}
        {live.mode === 'degraded' && (
          <p role="status">{t('实时通道不可用，已切换为轮询。')}</p>
        )}
        <div className="evaluation-actions">
          <Button onClick={refresh} disabled={loading}>
            {t('刷新结果')}
          </Button>
          <Link to={`/evaluations/${encodeURIComponent(evaluationId)}`}>
            {t('查看任务详情')}
          </Link>
        </div>
      </section>
      {!loading && current && (
        <section className="panel evaluation-panel" aria-label={t('评估结果')}>
          <div role="status" aria-label={t('结果可用性')}>
            <p>{availabilityLabels[availability?.kind ?? 'unknown']}</p>
            <p>
              {t('已记录 ')}
              {availability?.recorded_units ?? t('未知')} {t(' / 预期')}{' '}
              {availability?.expected_units ?? t('未知')} {t(' 单元')}
            </p>
            {availability?.kind === 'partial' && (
              <p>{t('以下为当前已记录的部分结果，统计尚非最终结果。')}</p>
            )}
            {['paused', 'failed', 'cancelled'].includes(
              availability?.kind ?? '',
            ) && (
              <p>
                {availability?.recorded_units
                  ? t('保留部分结果，统计不代表完整评估。')
                  : t('尚无已记录结果。')}
              </p>
            )}
            {availability?.kind === 'incomplete' && (
              <p>{t('任务已完成，但记录少于预期单元数。')}</p>
            )}
          </div>
          {current.resultError ? (
            <EvaluationFeedback
              message={t(current.resultError)}
              retry={refresh}
            />
          ) : (
            result && (
              <>
                <p>
                  {t('结果快照状态：')}
                  {resultStatusLabel(result.status)}
                  {t('；运行记录：')}
                  {result.run_id ?? t('未关联')}
                </p>
                <ResultTables result={result} />
                <nav
                  className="evaluation-pagination"
                  aria-label={t('单题结果分页')}
                >
                  <span>
                    {t('已记录 ')}
                    {result.problems.total} {t(' 个单元 ·')}{' '}
                    {result.problems.total
                      ? `${result.problems.offset + 1}–${result.problems.offset + result.problems.items.length} / ${result.problems.total}`
                      : '0 / 0'}
                  </span>
                  <Button
                    aria-label={t('上一页单题')}
                    disabled={page.offset === 0}
                    onClick={() =>
                      setSearch(
                        writeListQuery({
                          ...page,
                          offset: Math.max(0, page.offset - page.limit),
                        }),
                      )
                    }
                  >
                    {t('上一页')}
                  </Button>
                  <Button
                    aria-label={t('下一页单题')}
                    disabled={!result.problems.has_more}
                    onClick={() =>
                      setSearch(
                        writeListQuery({
                          ...page,
                          offset: page.offset + page.limit,
                        }),
                      )
                    }
                  >
                    {t('下一页')}
                  </Button>
                </nav>
              </>
            )
          )}
        </section>
      )}
    </section>
  )
}
