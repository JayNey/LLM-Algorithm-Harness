import { Alert, Button, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { useResource } from '../hooks/useResource.ts'
import { useTaskProgress } from '../experiments/useTaskProgress.ts'
import { ExperimentFeedback } from '../experiments/components.tsx'
import {
  assertRunAssociation,
  assertTaskAssociation,
  historySearch,
  readHistoryQuery,
  runStatuses,
  terminalRun,
  uniqueActiveRun,
} from './history.ts'
import {
  formatDateTime,
  formatRate,
  formatUsd,
  runStatusLabel,
} from './presentation.ts'
import type { BenchmarkClient } from './types.ts'

interface Props {
  client: BenchmarkClient
  owner: string | null
  suiteId: string
  revision: number
  onSettled: () => void
}

// The revision is a deliberate resource identity, separate from wire parameters.
function useVersionedResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  key: string,
) {
  const request = useMemo(() => ({ load, key }), [load, key])
  return useResource(
    useCallback((signal: AbortSignal) => request.load(signal), [request]),
  )
}

export default function RunHistory({
  client,
  owner,
  suiteId,
  revision,
  onSettled,
}: Props) {
  useTranslation()
  const [search, setSearch] = useSearchParams()
  const { runId, invalidRun, status, limit, offset } = readHistoryQuery(search)
  const [refresh, setRefresh] = useState(0)
  const history = useVersionedResource(
    useCallback(
      (signal: AbortSignal) =>
        client.runs(suiteId, { status, limit, offset }, signal),
      [client, suiteId, status, limit, offset],
    ),
    `${revision}:${refresh}`,
  )
  const active = useVersionedResource(
    useCallback(
      (signal: AbortSignal) =>
        Promise.all(
          (['pending', 'running', 'paused'] as const).map((status) =>
            client.runs(suiteId, { status, limit: 20, offset: 0 }, signal),
          ),
        ),
      [client, suiteId],
    ),
    `${revision}:${refresh}`,
  )
  const autoRun = active.data ? uniqueActiveRun(active.data) : null
  useEffect(() => {
    if (!runId && !invalidRun && autoRun)
      setSearch((previous) => historySearch(previous, { runId: autoRun }), {
        replace: true,
      })
  }, [autoRun, runId, invalidRun, setSearch])
  const reload = () => {
    setRefresh((v) => v + 1)
    onSettled()
  }
  const link = (id: string) => ({
    search: `?${historySearch(search, { runId: id })}`,
  })
  return (
    <section aria-label={t('运行历史')} className="benchmark-history">
      <h3>{t('运行历史')}</h3>
      <label>
        {t('历史状态筛选')}{' '}
        <Select
          aria-label={t('历史状态筛选')}
          value={status ?? ''}
          style={{ minWidth: 140 }}
          options={[
            { value: '', label: t('全部状态') },
            ...runStatuses.map((value) => ({
              value,
              label: runStatusLabel(value),
            })),
          ]}
          onChange={(value) =>
            setSearch((previous) =>
              historySearch(previous, { status: value, offset: 0 }),
            )
          }
        />
      </label>
      <Button onClick={reload}>{t('刷新历史')}</Button>
      {history.loading ? (
        <Skeleton active paragraph={{ rows: 2 }} />
      ) : history.error ? (
        <ExperimentFeedback message={t(history.error)} retry={history.retry} />
      ) : (
        history.data && (
          <>
            <p role="status">
              {t('共 {{total}} 次运行', { total: history.data.total })}
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table className="evaluation-list-table">
                <thead>
                  <tr>
                    {[
                      t('运行 ID'),
                      t('状态 / 错误'),
                      t('模型'),
                      t('准确率'),
                      t('成本'),
                      t('更新时间'),
                    ].map((label) => (
                      <th key={label} scope="col">
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {history.data.items.map((run) => (
                    <tr key={run.id}>
                      <td>
                        <Link
                          to={link(run.id)}
                          aria-current={run.id === runId ? 'true' : undefined}
                        >
                          {run.id}
                        </Link>
                      </td>
                      <td>{runStatusLabel(run.status)}</td>
                      <td>{run.model ?? '—'}</td>
                      <td>{formatRate(run.accuracy)}</td>
                      <td>{formatUsd(run.cost_usd)}</td>
                      <td>{formatDateTime(run.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {history.data.items.length === 0 && (
              <p role="status">{t('没有符合条件的运行')}</p>
            )}
            <div className="evaluation-section-heading">
              <Button
                disabled={offset === 0}
                onClick={() =>
                  setSearch((previous) =>
                    historySearch(previous, {
                      offset: Math.max(0, offset - limit),
                    }),
                  )
                }
              >
                {t('上一页')}
              </Button>
              <Button
                disabled={!history.data.has_more}
                onClick={() =>
                  setSearch((previous) =>
                    historySearch(previous, { offset: offset + limit }),
                  )
                }
              >
                {t('下一页')}
              </Button>
            </div>
          </>
        )
      )}
      {active.error ? (
        <ExperimentFeedback message={t(active.error)} retry={active.retry} />
      ) : (
        active.data &&
        active.data.some((p) => p.total > 0) && (
          <div>
            <h4>{t('活动运行')}</h4>
            {active.data.map((p, index) => (
              <div key={index}>
                {p.items.map((run) => (
                  <span
                    key={run.id}
                    style={{ display: 'inline-block', marginRight: 12 }}
                  >
                    <Link to={link(run.id)}>{run.id}</Link> ·{' '}
                    {runStatusLabel(run.status)}
                  </span>
                ))}
                {p.has_more && (
                  <Link
                    to={{
                      search: `?${historySearch(search, { status: (['pending', 'running', 'paused'] as const)[index], offset: 0 })}`,
                    }}
                  >
                    {t('查看更多活动运行')}
                  </Link>
                )}
              </div>
            ))}
          </div>
        )
      )}
      {invalidRun ? (
        <Alert
          role="alert"
          type="error"
          message={t('运行链接无效，请重新选择')}
        />
      ) : runId ? (
        <SelectedRun
          key={`${owner}:${suiteId}:${runId}`}
          client={client}
          owner={owner}
          suiteId={suiteId}
          runId={runId}
          revision={refresh}
          onSettled={onSettled}
        />
      ) : (
        <p role="status">{t('请选择运行以查看结果与进度')}</p>
      )}
    </section>
  )
}

function SelectedRun({
  client,
  owner,
  suiteId,
  runId,
  revision,
  onSettled,
}: Omit<Props, 'revision'> & { runId: string; revision: number }) {
  const detail = useVersionedResource(
    useCallback(
      async (signal: AbortSignal) =>
        assertRunAssociation(await client.run(runId, signal), suiteId, runId),
      [client, runId, suiteId],
    ),
    String(revision),
  )
  const run = detail.data
  const taskClient = useMemo(
    () => ({
      task: async (taskId: string, signal?: AbortSignal) =>
        assertTaskAssociation(await client.task(taskId, signal), taskId, runId),
    }),
    [client, runId],
  )
  const progress = useTaskProgress(
    taskClient,
    run && !terminalRun(run.status) ? run.task_id : null,
    owner,
  )
  const notified = useRef(new Set<string>())
  const terminal =
    progress.task && terminalRun(progress.task.status)
      ? progress.task.status
      : run && terminalRun(run.status)
        ? run.status
        : null
  useEffect(() => {
    if (!terminal || notified.current.has(terminal)) return
    notified.current.add(terminal)
    detail.retry()
    onSettled()
  }, [terminal, detail, onSettled])
  const paused = progress.task?.status === 'paused' || run?.status === 'paused'
  return (
    <section
      data-testid="selected-benchmark-run"
      style={{ overflowWrap: 'anywhere' }}
    >
      <h3>{t('选中运行')}</h3>
      <p>{runId}</p>
      <Button
        onClick={() => {
          detail.retry()
          progress.reload()
          onSettled()
        }}
      >
        {t('刷新运行')}
      </Button>
      {detail.loading ? (
        <Skeleton active paragraph={{ rows: 2 }} />
      ) : detail.error ? (
        <ExperimentFeedback message={t(detail.error)} retry={detail.retry} />
      ) : (
        run && (
          <>
            <p role="status">
              {runStatusLabel(run.status)} · {run.model ?? '—'} ·{' '}
              {formatRate(run.accuracy)} · {formatUsd(run.cost_usd)}
            </p>
            {(run.error_message || progress.task?.error_message) && (
              <Alert
                role="alert"
                type="error"
                message={run.error_message || progress.task?.error_message}
              />
            )}
            {progress.task?.progress && (
              <p role="status">
                {progress.task.progress.current_step} ·{' '}
                {progress.task.progress.current} /{' '}
                {progress.task.progress.total}（
                {progress.task.progress.percentage}%）
              </p>
            )}
            {paused && (
              <p role="status">{t('任务已暂停，可手动刷新运行状态')}</p>
            )}
            {!run.task_id && !terminalRun(run.status) && (
              <p role="status">{t('此运行没有关联任务，无法查询进度')}</p>
            )}
            {(progress.error || (progress.paused && !paused && !terminal)) && (
              <Alert
                role="alert"
                type="warning"
                message={t(progress.error || '进度查询已中断，请刷新运行重试')}
              />
            )}
            {run.results && Object.keys(run.results).length > 0 && (
              <details>
                <summary>{t('运行结果')}</summary>
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    maxHeight: 320,
                    overflow: 'auto',
                  }}
                >
                  {JSON.stringify(run.results, null, 2)}
                </pre>
              </details>
            )}
          </>
        )
      )}
    </section>
  )
}
