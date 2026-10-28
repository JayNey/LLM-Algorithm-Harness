import { useTranslation } from 'react-i18next'
import { currentLanguage, t } from '../../i18n/core.ts'
import { Button, Empty, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { EvaluationFeedback } from '@/evaluations/components.tsx'
import { evaluationLabel, metricLabel } from '@/evaluations/presentation.ts'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import type { Evaluation, ListQuery } from '@/evaluations/types.ts'
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

function TaskRow({ task }: { task: Evaluation }) {
  useTranslation()

  const progress = task.execution_progress
  const date = new Date(task.created_at)
  return (
    <tr>
      <td>
        <Link to={`/evaluations/${encodeURIComponent(task.evaluation_id)}`}>
          {task.evaluation_id}
        </Link>
        <small>{task.model ?? t('模型未知')}</small>
      </td>
      <td>
        {task.strategy_names.join('、') || t('策略未知')}
        <small>
          {task.problem_count} {t(' 道题目')}
        </small>
      </td>
      <td>
        <span>{evaluationLabel(task)}</span>
        <small>
          {progress.completed_units} / {progress.total_units} {t(' 单元 ·')}{' '}
          {progress.percentage}%
        </small>
      </td>
      <td>
        {metricLabel(task.spent_usd, 'USD')}
        <small>
          {task.budget_cap_usd === null
            ? t('未设置预算上限')
            : t('上限 {{value1}} USD', { value1: task.budget_cap_usd })}
        </small>
      </td>
      <td>
        <time dateTime={task.created_at}>
          {Number.isNaN(date.getTime())
            ? t('时间未知')
            : date.toLocaleString(currentLanguage())}
        </time>
      </td>
    </tr>
  )
}

export default function EvaluationsPage() {
  useTranslation()

  const { client, owner } = useEvaluationSession()
  const [search, setSearch] = useSearchParams()
  const rawSearch = search.toString()
  const query = useMemo(
    () => readListQuery(new URLSearchParams(rawSearch)),
    [rawSearch],
  )
  const load = useCallback(
    (query: ListQuery, signal: AbortSignal) => client.list(query, signal),
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
          <h1>{t('评估任务')}</h1>
          <p>{t('查看当前账号的评估任务与执行进度。')}</p>
        </div>
        <Link className="evaluation-create-link" to="/evaluations/new">
          {t('创建评估')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        <div className="evaluation-section-heading">
          <Select
            aria-label={t('任务状态')}
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
              {data.total} {t(' 个任务')}
            </span>
          )}
        </div>
        {loading ? (
          <div aria-busy="true">
            <p role="status">{t('正在加载评估任务…')}</p>
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
            aria-label={t('可滚动的评估任务列表')}
            tabIndex={0}
          >
            <table
              className="evaluation-list-table"
              aria-label={t('评估任务列表')}
            >
              <thead>
                <tr>
                  {[
                    t('任务 ID / 模型'),
                    t('策略 / 题目'),
                    t('状态 / 执行进度'),
                    t('费用'),
                    t('创建时间'),
                  ].map((name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((task) => (
                  <TaskRow key={task.evaluation_id} task={task} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            description={
              query.status ? t('没有符合筛选的评估任务') : t('还没有评估任务')
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
          <nav className="evaluation-pagination" aria-label={t('评估任务分页')}>
            <span>
              {data.total
                ? `${data.offset + 1}–${data.offset + data.items.length} / ${data.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label={t('上一页任务')}
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
              aria-label={t('下一页任务')}
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
