import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button, Empty, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { EvaluationFeedback } from '@/evaluations/components.tsx'
import { resultStatusLabel } from '@/evaluations/presentation.ts'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import type { ResultSummary, ListQuery } from '@/evaluations/types.ts'
import { useList } from '@/evaluations/useList.ts'
import { readListQuery, writeListQuery } from '@/evaluations/validation.ts'
import '@/evaluations/workflow.css'

const statusOptions = [
  {
    value: 'all',
    get label() {
      return t('全部状态')
    },
  },
  {
    value: 'pending',
    get label() {
      return t('待执行')
    },
  },
  {
    value: 'running',
    get label() {
      return t('运行中')
    },
  },
  {
    value: 'paused',
    get label() {
      return t('已暂停')
    },
  },
  {
    value: 'completed',
    get label() {
      return t('已完成')
    },
  },
  {
    value: 'failed',
    get label() {
      return t('失败')
    },
  },
  {
    value: 'cancelled',
    get label() {
      return t('已取消')
    },
  },
]

function ResultRow({ result }: { result: ResultSummary }) {
  useTranslation()

  return (
    <tr>
      <td>
        <Link to={`/results/${encodeURIComponent(result.id)}`}>
          {result.id}
        </Link>
        <small>{result.model ?? t('模型未知')}</small>
      </td>
      <td>{result.strategy_names.join('、') || t('策略未知')}</td>
      <td>{resultStatusLabel(result.status)}</td>
      <td>
        <time dateTime={result.created_at}>{result.created_at}</time>
      </td>
      <td>{result.completed_at ?? t('未知')}</td>
    </tr>
  )
}

export default function ResultsPage() {
  useTranslation()

  const { client, owner } = useEvaluationSession()
  const [search, setSearch] = useSearchParams()
  const rawSearch = search.toString()
  const query = useMemo(
    () => readListQuery(new URLSearchParams(rawSearch)),
    [rawSearch],
  )
  const load = useCallback(
    (query: ListQuery, signal: AbortSignal) => client.results(query, signal),
    [client],
  )
  const list = useList(load, query, owner ?? '')
  const data = list.data
  const outOfRange = !!data && query.offset > 0 && query.offset >= data.total
  useEffect(() => {
    const next = writeListQuery(
      outOfRange && data
        ? {
            ...query,
            offset:
              Math.floor(Math.max(0, data.total - 1) / query.limit) *
              query.limit,
          }
        : query,
    )
    if (next.toString() !== rawSearch) setSearch(next, { replace: true })
  }, [query, rawSearch, setSearch, data, outOfRange])
  const loading = list.status === 'loading' || outOfRange
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('评估结果')}</h1>
          <p>{t('查看当前账号已记录的评估结果。')}</p>
        </div>
        <Link className="evaluation-create-link" to="/evaluations/new">
          {t('创建评估')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        <div className="evaluation-section-heading">
          <Select
            aria-label={t('结果状态')}
            value={query.status ?? 'all'}
            options={statusOptions.map((option) => ({ ...option }))}
            onChange={(status: string) =>
              setSearch(
                writeListQuery({
                  limit: query.limit,
                  offset: 0,
                  ...(status !== 'all' ? { status } : {}),
                }),
              )
            }
          />
          {data && !loading && (
            <span role="status">
              {t('共 ')}
              {data.total} {t(' 个结果')}
            </span>
          )}
        </div>
        {loading ? (
          <div aria-busy="true">
            <p role="status">{t('正在加载评估结果…')}</p>
            <Skeleton active paragraph={{ rows: 4 }} />
          </div>
        ) : list.status === 'error' ? (
          <EvaluationFeedback
            message={t(list.error ?? t('加载失败，请重试'))}
            retry={list.reload}
          />
        ) : data?.items.length ? (
          <div
            className="evaluation-list-scroll"
            role="region"
            aria-label={t('可滚动的评估结果列表')}
            tabIndex={0}
          >
            <table
              className="evaluation-list-table"
              aria-label={t('评估结果列表')}
            >
              <thead>
                <tr>
                  {[
                    t('评估 ID / 模型'),
                    t('策略'),
                    t('状态'),
                    t('创建时间'),
                    t('完成时间'),
                  ].map((name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((result) => (
                  <ResultRow key={result.id} result={result} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            description={
              query.status ? t('没有符合筛选的评估结果') : t('还没有评估结果')
            }
          >
            {query.status && (
              <Button
                onClick={() =>
                  setSearch(writeListQuery({ limit: query.limit, offset: 0 }))
                }
              >
                {t('清除筛选')}
              </Button>
            )}
            <Link to="/evaluations/new">{t('创建首个评估')}</Link>
          </Empty>
        )}
        {data && !loading && (
          <nav className="evaluation-pagination" aria-label={t('评估结果分页')}>
            <span>
              {data.total
                ? `${data.offset + 1}–${data.offset + data.items.length} / ${data.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label={t('上一页结果')}
              disabled={query.offset === 0}
              onClick={() =>
                setSearch(
                  writeListQuery({
                    ...query,
                    offset: Math.max(0, query.offset - query.limit),
                  }),
                )
              }
            >
              {t('上一页')}
            </Button>
            <Button
              aria-label={t('下一页结果')}
              disabled={!data.has_more}
              onClick={() =>
                setSearch(
                  writeListQuery({
                    ...query,
                    offset: query.offset + query.limit,
                  }),
                )
              }
            >
              {t('下一页')}
            </Button>
          </nav>
        )}
      </div>
    </section>
  )
}
