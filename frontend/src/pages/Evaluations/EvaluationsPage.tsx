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
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '运行中' },
  { value: 'paused', label: '已暂停' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

function TaskRow({ task }: { task: Evaluation }) {
  const progress = task.execution_progress
  const date = new Date(task.created_at)
  return (
    <tr>
      <td>
        <Link to={`/evaluations/${encodeURIComponent(task.evaluation_id)}`}>
          {task.evaluation_id}
        </Link>
        <small>{task.model ?? '模型未知'}</small>
      </td>
      <td>
        {task.strategy_names.join('、') || '策略未知'}
        <small>{task.problem_count} 道题目</small>
      </td>
      <td>
        <span>{evaluationLabel(task)}</span>
        <small>
          {progress.completed_units} / {progress.total_units} 单元 ·{' '}
          {progress.percentage}%
        </small>
      </td>
      <td>
        {metricLabel(task.spent_usd, 'USD')}
        <small>
          {task.budget_cap_usd === null
            ? '未设置预算上限'
            : `上限 ${task.budget_cap_usd} USD`}
        </small>
      </td>
      <td>
        <time dateTime={task.created_at}>
          {Number.isNaN(date.getTime())
            ? '时间未知'
            : date.toLocaleString('zh-CN')}
        </time>
      </td>
    </tr>
  )
}

export default function EvaluationsPage() {
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
          <h1>评估任务</h1>
          <p>查看当前账号的评估任务与执行进度。</p>
        </div>
        <Link className="evaluation-create-link" to="/evaluations/new">
          创建评估
        </Link>
      </header>
      <div className="panel evaluation-panel">
        <div className="evaluation-section-heading">
          <Select
            aria-label="任务状态"
            value={query.status ?? 'all'}
            options={statusOptions}
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
            <span role="status">共 {data.total} 个任务</span>
          )}
        </div>
        {loading ? (
          <div aria-busy="true">
            <p role="status">正在加载评估任务…</p>
            <Skeleton active paragraph={{ rows: 4 }} />
          </div>
        ) : list.status === 'error' ? (
          <EvaluationFeedback
            message={list.error ?? '加载失败，请重试'}
            retry={list.reload}
          />
        ) : data?.items.length ? (
          <div
            className="evaluation-list-scroll"
            role="region"
            aria-label="可滚动的评估任务列表"
            tabIndex={0}
          >
            <table className="evaluation-list-table" aria-label="评估任务列表">
              <thead>
                <tr>
                  {[
                    '任务 ID / 模型',
                    '策略 / 题目',
                    '状态 / 执行进度',
                    '费用',
                    '创建时间',
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
              query.status ? '没有符合筛选的评估任务' : '还没有评估任务'
            }
          >
            {query.status && (
              <Button
                onClick={() =>
                  setSearch(writeListQuery({ limit: query.limit, offset: 0 }))
                }
              >
                清除筛选
              </Button>
            )}
            <Link to="/evaluations/new">创建首个评估</Link>
          </Empty>
        )}
        {data && !loading && (
          <nav className="evaluation-pagination" aria-label="评估任务分页">
            <span>
              {data.total
                ? `${data.offset + 1}–${data.offset + data.items.length} / ${data.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label="上一页任务"
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
              上一页
            </Button>
            <Button
              aria-label="下一页任务"
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
              下一页
            </Button>
          </nav>
        )}
      </div>
    </section>
  )
}
