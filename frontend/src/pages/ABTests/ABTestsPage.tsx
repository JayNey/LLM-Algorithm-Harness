import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button, Empty, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useList } from '@/evaluations/useList.ts'
import { formatDateTime, statusLabel } from '@/abtests/presentation.ts'
import { useABTestSession } from '@/abtests/session.tsx'
import type { ABTestJob, ListQuery } from '@/abtests/types.ts'
import { readListQuery, writeListQuery } from '@/abtests/validation.ts'

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

function ABTestRow({
  test,
  onDeleted,
}: {
  test: ABTestJob
  onDeleted: () => void
}) {
  useTranslation()

  const { client } = useABTestSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function remove() {
    if (busy) return
    if (
      !window.confirm(
        t('确认删除 A/B 测试「{{value1}}」？', {
          value1: test.name || test.id,
        }),
      )
    )
      return
    setBusy(true)
    setError(null)
    try {
      await client.remove(test.id)
      onDeleted()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '删除失败，请重试')
    } finally {
      setBusy(false)
    }
  }
  return (
    <tr>
      <td>
        <Link to={`/ab-tests/${encodeURIComponent(test.id)}`}>{test.id}</Link>
        <small>{test.name || t('未命名测试')}</small>
      </td>
      <td>
        {test.config.model.model}
        <small>
          {t('策略 ')}
          {test.config.strategy.name}
        </small>
      </td>
      <td>
        <span>{statusLabel(test.status)}</span>
        <small>
          {t('变体')}{' '}
          {test.config.prompt_variants.map((variant) => variant.id).join(' / ')}
        </small>
      </td>
      <td>
        <time dateTime={test.created_at}>
          {formatDateTime(test.created_at)}
        </time>
        <small>{test.error_message ?? ''}</small>
      </td>
      <td>
        <Button
          size="small"
          danger
          disabled={busy}
          onClick={() => void remove()}
        >
          {t('删除')}
        </Button>
        {error && (
          <small role="alert" style={{ color: '#cf1322' }}>
            {t(error)}
          </small>
        )}
      </td>
    </tr>
  )
}

export default function ABTestsPage() {
  useTranslation()

  const { client, owner } = useABTestSession()
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
  const list = useList<ABTestJob>(load, query, owner ?? '')
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
          <h1>{t('A/B 测试')}</h1>
          <p>{t('同一模型下的双提示词变体对比与统计检验。')}</p>
        </div>
        <Link className="evaluation-create-link" to="/ab-tests/new">
          {t('新建 A/B 测试')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        <div className="evaluation-section-heading">
          <Select
            aria-label={t('A/B 测试状态')}
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
              {data.total} {t(' 个测试')}
            </span>
          )}
        </div>
        {loading ? (
          <div aria-busy="true">
            <p role="status">{t('正在加载 A/B 测试…')}</p>
            <Skeleton active paragraph={{ rows: 4 }} />
          </div>
        ) : list.status === 'error' ? (
          <ExperimentFeedback
            message={t(list.error ?? t('加载失败，请重试'))}
            retry={list.reload}
          />
        ) : data?.items.length ? (
          <table
            className="evaluation-list-table"
            aria-label={t('A/B 测试列表')}
          >
            <thead>
              <tr>
                {[
                  t('测试 ID / 名称'),
                  t('模型 / 策略'),
                  t('状态 / 变体'),
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
              {data.items.map((test) => (
                <ABTestRow key={test.id} test={test} onDeleted={list.reload} />
              ))}
            </tbody>
          </table>
        ) : (
          <Empty
            description={
              query.status ? t('没有符合筛选的测试') : t('还没有 A/B 测试')
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
            <Link to="/ab-tests/new">{t('创建首个 A/B 测试')}</Link>
          </Empty>
        )}
        {data && !loading && (
          <nav className="evaluation-pagination" aria-label={t('A/B 测试分页')}>
            <span>
              {data.total
                ? `${data.offset + 1}–${data.offset + data.items.length} / ${data.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label={t('上一页测试')}
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
              aria-label={t('下一页测试')}
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
