import { Alert, Button, Input, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useSystemLogSession } from '@/systemlogs/session.tsx'
import type { LogPage } from '@/systemlogs/types.ts'
import { readLogQuery } from '@/systemlogs/client.ts'

const LEVEL_OPTIONS = [
  { value: '', label: '全部级别' },
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'CRITICAL', label: 'CRITICAL' },
]

const LEVEL_COLOR: Record<string, string> = {
  ERROR: '#cf1322',
  CRITICAL: '#cf1322',
  WARNING: '#d46b08',
}

export default function SystemLogsPage() {
  const { client } = useSystemLogSession()
  const [filters, setFilters] = useState({
    level: '',
    search: '',
    start: '',
    end: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<LogPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [denied, setDenied] = useState(false)

  const query = readLogQuery(filters)
  const load = useCallback(
    (signal: AbortSignal) => client.query({ ...query.query, offset }, signal),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 过滤器变化经提交按钮触发（attempt）
    [client, offset, filters],
  )
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const operation = attempt
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted && operation === attempt) {
          setPage(data)
          setError(null)
        }
      },
      (cause: unknown) => {
        if (controller.signal.aborted || operation !== attempt) return
        if (cause instanceof Error && cause.message.includes('403')) {
          setDenied(true)
        } else {
          setError(cause instanceof Error ? cause.message : '查询失败，请重试')
        }
      },
    )
    return () => controller.abort()
  }, [load, attempt])

  function submit() {
    const next = readLogQuery(filters)
    setErrors(next.errors)
    if (Object.keys(next.errors).length) return
    setOffset(0)
    setAttempt((value) => value + 1)
  }

  if (denied) {
    return (
      <section className="mx-auto w-full max-w-3xl">
        <Alert type="error" message="无权访问系统日志（仅管理员）。" showIcon />
        <p className="mt-6">
          <Link to="/settings">返回设置</Link>
        </p>
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-4xl">
      <h1 className="mb-2 text-xl font-semibold">系统日志</h1>
      <p className="mb-6 text-neutral-600 dark:text-neutral-400">
        仅管理员可查询；保留近期 API 生命周期与任务事件。不支持实时流与下载。
      </p>
      <div className="evaluation-section-heading mb-4">
        <Select
          aria-label="日志级别"
          value={filters.level}
          options={LEVEL_OPTIONS}
          onChange={(value: string) => setFilters({ ...filters, level: value })}
        />
        <Input
          aria-label="搜索关键词"
          placeholder="搜索消息（≤200 字）"
          maxLength={200}
          value={filters.search}
          onChange={(event) =>
            setFilters({ ...filters, search: event.target.value })
          }
        />
        <label>
          起
          <Input
            aria-label="起始时间"
            type="datetime-local"
            value={filters.start}
            onChange={(event) =>
              setFilters({ ...filters, start: event.target.value })
            }
          />
          {errors.start && <small role="alert">{errors.start}</small>}
        </label>
        <label>
          止
          <Input
            aria-label="结束时间"
            type="datetime-local"
            value={filters.end}
            onChange={(event) =>
              setFilters({ ...filters, end: event.target.value })
            }
          />
          {errors.end && <small role="alert">{errors.end}</small>}
        </label>
        <Button type="primary" aria-label="查询日志" onClick={submit}>
          查询
        </Button>
      </div>
      {error ? (
        <ExperimentFeedback
          message={error}
          retry={() => setAttempt((v) => v + 1)}
        />
      ) : page === null ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : page.items.length ? (
        <>
          <div
            className="evaluation-list-scroll"
            role="region"
            aria-label="日志列表"
            tabIndex={0}
          >
            <table className="evaluation-list-table" aria-label="系统日志">
              <thead>
                <tr>
                  {['时间', '级别', '消息', '用户', '运行'].map((name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {page.items.map((entry) => (
                  <tr key={entry.id}>
                    <td>
                      {new Date(entry.timestamp * 1000).toLocaleString('zh-CN')}
                    </td>
                    <td style={{ color: LEVEL_COLOR[entry.level] }}>
                      {entry.level}
                    </td>
                    <td>{entry.message}</td>
                    <td>{entry.user_id ?? '—'}</td>
                    <td>{entry.run_id ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="evaluation-pagination" aria-label="日志分页">
            <span>
              {page.total
                ? `${page.offset + 1}–${page.offset + page.items.length} / ${page.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label="上一页日志"
              disabled={page.offset === 0}
              onClick={() => {
                setOffset(Math.max(0, page.offset - page.limit))
                setAttempt((v) => v + 1)
              }}
            >
              上一页
            </Button>
            <Button
              aria-label="下一页日志"
              disabled={page.offset + page.limit >= page.total}
              onClick={() => {
                setOffset(page.offset + page.limit)
                setAttempt((v) => v + 1)
              }}
            >
              下一页
            </Button>
          </nav>
        </>
      ) : (
        <p role="status">没有匹配的日志记录。</p>
      )}
      <p className="mt-6">
        <Link to="/settings">返回设置</Link>
      </p>
    </section>
  )
}
