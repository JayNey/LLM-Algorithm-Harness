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
import { resultStatusLabel } from '@/evaluations/presentation.ts'
import { useAuthStore } from '@/store/auth.ts'
import '@/evaluations/workflow.css'

export default function ResultDetailPage() {
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
  const live = useEvaluationLive(client, evaluationId, owner, liveEnabled, load)
  const current =
    live.forbidden || live.unauthorized
      ? undefined
      : (live.evaluation ?? bootstrap.data)
  const error = live.forbidden
    ? '任务不可访问，请刷新后重试'
    : (live.error ?? bootstrap.error)
  const result = current?.result
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
          <h1>评估结果详情</h1>
          <p>查看任务事实、全量策略统计与已记录的单题结果。</p>
        </div>
        <Link to="/results">返回结果列表</Link>
      </header>
      <section
        className="panel evaluation-panel"
        aria-label="任务信息"
        aria-busy={loading}
      >
        <dl className="evaluation-receipt">
          <dt>评估 ID</dt>
          <dd>{evaluationId}</dd>
        </dl>
        {loading && <p role="status">正在加载评估结果…</p>}
        {error && (
          <EvaluationFeedback
            message={current ? `${error}；下方为上次读取的数据。` : error}
            retry={refresh}
          />
        )}
        {current && <EvaluationFacts evaluation={current} />}
        {live.mode === 'live' && <p role="status">实时进度已连接</p>}
        {live.mode === 'degraded' && (
          <p role="status">实时通道不可用，已切换为轮询。</p>
        )}
        <div className="evaluation-actions">
          <Button onClick={refresh} disabled={loading}>
            刷新结果
          </Button>
          <Link to={`/evaluations/${encodeURIComponent(evaluationId)}`}>
            查看任务详情
          </Link>
        </div>
      </section>
      {!loading && current && (
        <section className="panel evaluation-panel" aria-label="评估结果">
          {current.resultError ? (
            <EvaluationFeedback message={current.resultError} retry={refresh} />
          ) : (
            result && (
              <>
                <p>
                  结果快照状态：{resultStatusLabel(result.status)}；运行记录：
                  {result.run_id ?? '未关联'}
                </p>
                <ResultTables result={result} />
                <nav
                  className="evaluation-pagination"
                  aria-label="单题结果分页"
                >
                  <span>
                    已记录 {result.problems.total} 个单元 ·{' '}
                    {result.problems.total
                      ? `${result.problems.offset + 1}–${result.problems.offset + result.problems.items.length} / ${result.problems.total}`
                      : '0 / 0'}
                  </span>
                  <Button
                    aria-label="上一页单题"
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
                    上一页
                  </Button>
                  <Button
                    aria-label="下一页单题"
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
                    下一页
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
