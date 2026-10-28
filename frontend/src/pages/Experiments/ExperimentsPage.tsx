import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button, Empty, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { formatDateTime, statusLabel } from '@/experiments/presentation.ts'
import { useExperimentSession } from '@/experiments/session.tsx'
import type { ExperimentJob, ListQuery } from '@/experiments/types.ts'
import { useList } from '@/evaluations/useList.ts'
import { readListQuery, writeListQuery } from '@/experiments/validation.ts'

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
      return t('排队中')
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
      return t('已失败')
    },
  },
  {
    value: 'cancelled',
    get label() {
      return t('已取消')
    },
  },
]

function ExperimentRow({
  job,
  onSettled,
}: {
  job: ExperimentJob
  onSettled: () => void
}) {
  useTranslation()

  const { client } = useExperimentSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const running = job.status === 'running' || job.status === 'paused'
  async function cancel() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const tasks = await client.runningExperimentTasks()
      const task = tasks.find((item) => item.entity_id === job.id)
      if (!task) {
        setError('未找到该实验的运行任务')
        return
      }
      await client.cancelTask(task.id)
      onSettled()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '取消失败，请重试')
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (busy) return
    if (
      !window.confirm(
        t('确认删除实验「{{value1}}」？', { value1: job.name || job.id }),
      )
    )
      return
    setBusy(true)
    setError(null)
    try {
      await client.remove(job.id)
      onSettled()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '删除失败，请重试')
    } finally {
      setBusy(false)
    }
  }
  return (
    <tr>
      <td>
        <Link to={`/experiments/${encodeURIComponent(job.id)}`}>{job.id}</Link>
        <small>{job.name || t('未命名实验')}</small>
      </td>
      <td>
        {job.config.models.map((model) => model.model).join('、') ||
          t('模型未知')}
        <small>
          {job.config.strategies.map((strategy) => strategy.name).join('、') ||
            t('策略未知')}
        </small>
      </td>
      <td>
        <span>{statusLabel(job.status)}</span>
        <small>
          {t('重复 ')}
          {job.config.repeats} {t(' 次 ·')}{' '}
          {job.config.execution === 'parallel'
            ? t('并行 ×{{value1}}', { value1: job.config.max_workers })
            : t('串行')}
        </small>
      </td>
      <td>
        <time dateTime={job.created_at}>{formatDateTime(job.created_at)}</time>
        <small>{job.error_message ?? ''}</small>
      </td>
      <td>
        {running && (
          <Button size="small" disabled={busy} onClick={() => void cancel()}>
            {t('取消运行')}
          </Button>
        )}
        {!running && (
          <Button
            size="small"
            danger
            disabled={busy}
            onClick={() => void remove()}
          >
            {t('删除')}
          </Button>
        )}
        {error && (
          <small role="alert" style={{ color: '#cf1322' }}>
            {t(error)}
          </small>
        )}
      </td>
    </tr>
  )
}

export default function ExperimentsPage() {
  useTranslation()

  const { client, owner } = useExperimentSession()
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
  const list = useList<ExperimentJob>(load, query, owner ?? '')
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
          <h1>{t('实验管理')}</h1>
          <p>{t('固定预算对比实验的创建、运行与对比分析。')}</p>
        </div>
        <Link className="evaluation-create-link" to="/experiments/new">
          {t('创建实验')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        <div className="evaluation-section-heading">
          <Select
            aria-label={t('实验状态')}
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
              {data.total} {t(' 个实验')}
            </span>
          )}
        </div>
        {loading ? (
          <div aria-busy="true">
            <p role="status">{t('正在加载实验…')}</p>
            <Skeleton active paragraph={{ rows: 4 }} />
          </div>
        ) : list.status === 'error' ? (
          <ExperimentFeedback
            message={t(list.error ?? t('加载失败，请重试'))}
            retry={list.reload}
          />
        ) : data?.items.length ? (
          <div
            className="evaluation-list-scroll"
            role="region"
            aria-label={t('可滚动的实验列表')}
            tabIndex={0}
          >
            <table className="evaluation-list-table" aria-label={t('实验列表')}>
              <thead>
                <tr>
                  {[
                    t('实验 ID / 名称'),
                    t('模型 / 策略'),
                    t('状态 / 执行'),
                    t('创建时间'),
                    t('操作'),
                  ].map((name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((job) => (
                  <ExperimentRow
                    key={job.id}
                    job={job}
                    onSettled={list.reload}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            description={
              query.status ? t('没有符合筛选的实验') : t('还没有实验')
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
            <Link to="/experiments/new">{t('创建首个实验')}</Link>
          </Empty>
        )}
        {data && !loading && (
          <nav className="evaluation-pagination" aria-label={t('实验分页')}>
            <span>
              {data.total
                ? `${data.offset + 1}–${data.offset + data.items.length} / ${data.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label={t('上一页实验')}
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
              aria-label={t('下一页实验')}
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
