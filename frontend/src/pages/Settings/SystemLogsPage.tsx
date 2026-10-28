import { useTranslation } from 'react-i18next'
import { currentLanguage, t } from '../../i18n/core.ts'
import { Alert, Button, Input, Select, Skeleton } from 'antd'
import { useEffect, useState } from 'react'
import { ApiClientError } from '@/auth/http.ts'
import { Link } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useSystemLogSession } from '@/systemlogs/session.tsx'
import type { LogPage, LogQuery } from '@/systemlogs/types.ts'
import { readLogQuery } from '@/systemlogs/client.ts'

const LEVEL_OPTIONS = [
  {
    value: '',
    get label() {
      return t('全部级别')
    },
  },
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
  useTranslation()

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

  const [committed, setCommitted] = useState<LogQuery>({ limit: 50, offset: 0 })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const operation = attempt
    void client
      .query({ ...committed, offset }, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && operation === attempt) {
          setPage(data)
          setError(null)
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted || operation !== attempt) return
        if (cause instanceof ApiClientError && cause.status === 403) {
          setDenied(true)
        } else {
          setError(cause instanceof Error ? cause.message : '查询失败，请重试')
        }
      })
    return () => controller.abort()
  }, [client, committed, offset, attempt])

  function submit() {
    const next = readLogQuery(filters)
    setErrors(next.errors)
    if (Object.keys(next.errors).length) return
    setOffset(0)
    // 提交时固化查询快照（filters 引用不进 effect 依赖，防逐键请求竞态）
    setCommitted(next.query)
    setAttempt((value) => value + 1)
  }

  if (denied) {
    return (
      <section className="mx-auto w-full max-w-3xl">
        <Alert
          type="error"
          message={t('无权访问系统日志（仅管理员）。')}
          showIcon
        />
        <p className="mt-6">
          <Link to="/settings">{t('返回设置')}</Link>
        </p>
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-4xl">
      <h1 className="mb-2 text-xl font-semibold">{t('系统日志')}</h1>
      <p className="mb-6 text-neutral-600 dark:text-neutral-400">
        {t(
          '仅管理员可查询；保留近期 API 生命周期与任务事件。不支持实时流与下载。',
        )}
      </p>
      <div className="evaluation-section-heading mb-4">
        <Select
          aria-label={t('日志级别')}
          value={filters.level}
          options={LEVEL_OPTIONS.map((option) => ({ ...option }))}
          onChange={(value: string) => setFilters({ ...filters, level: value })}
        />
        <Input
          aria-label={t('搜索关键词')}
          placeholder={t('搜索消息（≤200 字）')}
          maxLength={200}
          value={filters.search}
          onChange={(event) =>
            setFilters({ ...filters, search: event.target.value })
          }
        />
        <label>
          {t('起')}
          <Input
            aria-label={t('起始时间')}
            type="datetime-local"
            value={filters.start}
            onChange={(event) =>
              setFilters({ ...filters, start: event.target.value })
            }
          />
          {errors.start && <small role="alert">{t(errors.start)}</small>}
        </label>
        <label>
          {t('止')}
          <Input
            aria-label={t('结束时间')}
            type="datetime-local"
            value={filters.end}
            onChange={(event) =>
              setFilters({ ...filters, end: event.target.value })
            }
          />
          {errors.end && <small role="alert">{t(errors.end)}</small>}
        </label>
        <Button type="primary" aria-label={t('查询日志')} onClick={submit}>
          {t('查询')}
        </Button>
      </div>
      {error ? (
        <ExperimentFeedback
          message={t(error)}
          retry={() => setAttempt((v) => v + 1)}
        />
      ) : page === null ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : page.items.length ? (
        <>
          <div
            className="evaluation-list-scroll"
            role="region"
            aria-label={t('日志列表')}
            tabIndex={0}
          >
            <table className="evaluation-list-table" aria-label={t('系统日志')}>
              <thead>
                <tr>
                  {[t('时间'), t('级别'), t('消息'), t('用户'), t('运行')].map(
                    (name) => (
                      <th key={name} scope="col">
                        {name}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {page.items.map((entry) => (
                  <tr key={entry.id}>
                    <td>
                      {new Date(entry.timestamp * 1000).toLocaleString(
                        currentLanguage(),
                      )}
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
          <nav className="evaluation-pagination" aria-label={t('日志分页')}>
            <span>
              {page.total
                ? `${page.offset + 1}–${page.offset + page.items.length} / ${page.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label={t('上一页日志')}
              disabled={page.offset === 0}
              onClick={() => {
                setOffset(Math.max(0, page.offset - page.limit))
                setAttempt((v) => v + 1)
              }}
            >
              {t('上一页')}
            </Button>
            <Button
              aria-label={t('下一页日志')}
              disabled={page.offset + page.limit >= page.total}
              onClick={() => {
                setOffset(page.offset + page.limit)
                setAttempt((v) => v + 1)
              }}
            >
              {t('下一页')}
            </Button>
          </nav>
        </>
      ) : (
        <p role="status">{t('没有匹配的日志记录。')}</p>
      )}
      <p className="mt-6">
        <Link to="/settings">{t('返回设置')}</Link>
      </p>
    </section>
  )
}
