import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Drawer, Select, Skeleton, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useList } from '@/evaluations/useList.ts'
import {
  difficultyLabel,
  formatRate,
  historyStatusLabel,
  importStatusLabel,
  sourceLabel,
} from '@/problems/presentation.ts'
import { useProblemSession } from '@/problems/session.tsx'
import type {
  ApiPage,
  DirectImportResult,
  ImportJobProgress,
  ImportMode,
  ImportValidation,
  ProblemHistoryItem,
  ProblemListQuery,
  ProblemOption,
} from '@/problems/types.ts'
import {
  DIRECT_IMPORT_MAX_BYTES,
  validateImportFile,
} from '@/problems/client.ts'
import {
  canSubmitImport,
  isImportTerminalStatus,
} from '@/problems/importSubmission.ts'
import {
  readListQuery,
  setProblemImportIntent,
  writeProblemListQuery,
} from '@/problems/validation.ts'
import '@/evaluations/workflow.css'

const IMPORT_POLL_MS = 3_000

function ValidationReport({ report }: { report: ImportValidation }) {
  useTranslation()

  return (
    <div role="status" aria-label={t('导入报告')}>
      <p>
        {t('共 ')}
        {report.total} {t(' 条 · 有效 ')}
        {report.valid} {t(' · 无效 ')}
        {report.invalid} {t(' · 重复 ')}
        {report.duplicates} {t(' · 本次导入 ')}
        {report.imported} {t(' · 个人库存量')} {report.dataset_total}
      </p>
      {report.invalid > 0 && (
        <>
          <h4>{t('错误明细')}</h4>
          <ul>
            {report.errors.map((error, index) => (
              <li key={index}>
                {t('第 ')}
                {error.index + 1} {t(' 条：')}
                {error.errors
                  .map((detail) => `${detail.field}（${detail.type}）`)
                  .join('、') || t('格式无效')}
              </li>
            ))}
          </ul>
          {report.errors_truncated && <p>{t('错误过多，仅显示前 200 条。')}</p>}
        </>
      )}
    </div>
  )
}

function ImportPanel({
  onImported,
  onClose,
}: {
  onImported: () => void
  onClose: () => void
}) {
  useTranslation()

  const { client } = useProblemSession()
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState<ImportMode>('append')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<ImportValidation | null>(null)
  const [progress, setProgress] = useState<ImportJobProgress | null>(null)
  const submitLock = useRef(false)
  const pollFailures = useRef(0)

  useEffect(() => {
    // 异步导入轮询：终态停止；失败重试有上限（连续 3 次无进展则停并提示）
    if (!progress || isImportTerminalStatus(progress.status)) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      void client
        .importJob(progress.job_id, controller.signal)
        .then((next) => {
          pollFailures.current = 0
          setProgress(next)
          if (isImportTerminalStatus(next.status)) submitLock.current = false
          if (next.status === 'completed' && next.result) {
            setReport(next.result)
            onImported()
          } else if (next.status === 'failed') {
            setError(
              next.failureDetail
                ? t('导入任务失败：{{value1}}', { value1: next.failureDetail })
                : '导入任务失败，请检查文件格式后重试。',
            )
          }
        })
        .catch(() => {
          pollFailures.current += 1
          if (pollFailures.current >= 3) {
            setError('进度查询连续失败，请稍后刷新页面查看导入结果。')
            return
          }
          // 触发重排：同对象新引用让 effect 重新调度下一周期
          setProgress({ ...progress })
        })
    }, IMPORT_POLL_MS)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [client, progress, onImported])

  function submit() {
    const selectedFile = file
    if (
      !selectedFile ||
      !canSubmitImport(true, busy, progress?.status ?? null, submitLock.current)
    )
      return
    pollFailures.current = 0
    const fileError = validateImportFile({
      name: selectedFile.name,
      size: selectedFile.size,
    })
    if (fileError) {
      setError(fileError)
      return
    }
    if (
      mode === 'overwrite' &&
      !window.confirm(t('overwrite 将整库替换个人题库，确认继续？'))
    ) {
      return
    }
    submitLock.current = true
    setBusy(true)
    setError(null)
    setReport(null)
    setProgress(null)
    const finish = () => {
      submitLock.current = false
      setBusy(false)
    }
    if (selectedFile.size <= DIRECT_IMPORT_MAX_BYTES) {
      client
        .directImport(selectedFile, mode)
        .then((result: DirectImportResult) => {
          setReport(result.validation)
          onImported()
        })
        .catch((cause: unknown) =>
          setError(cause instanceof Error ? cause.message : '导入失败，请重试'),
        )
        .finally(finish)
    } else {
      let awaitingTerminal = false
      client
        .uploadFile(selectedFile)
        .then((uploaded) => client.startImport(uploaded.file_id, mode))
        .then((started) => {
          awaitingTerminal = !isImportTerminalStatus(started.status)
          setProgress({
            job_id: started.job_id,
            status: started.status,
            processed: 0,
            total: 0,
            percentage: 0,
            result: null,
            failureDetail: null,
          })
          if (!awaitingTerminal) submitLock.current = false
        })
        .catch((cause: unknown) =>
          setError(cause instanceof Error ? cause.message : '导入失败，请重试'),
        )
        .finally(() => {
          if (!awaitingTerminal) submitLock.current = false
          setBusy(false)
        })
    }
  }

  return (
    <div className="panel evaluation-panel" aria-label={t('题目导入')}>
      <h3>{t('导入题目（个人题库）')}</h3>
      <p>
        {t('支持 JSON / CSV 文件；小于 5MiB 直接导入，大文件转入后台任务。')}
      </p>
      {error && <Alert role="alert" type="error" message={t(error)} />}
      <Upload
        aria-label={t('导入文件选择')}
        maxCount={1}
        beforeUpload={(selected: File) => {
          setFile(selected)
          return false
        }}
        onRemove={() => setFile(null)}
        fileList={
          file
            ? [
                {
                  uid: '-1',
                  name: file.name,
                  status: 'done',
                } satisfies UploadFile,
              ]
            : []
        }
      >
        <Button aria-label={t('选择导入文件')}>{t('选择文件')}</Button>
      </Upload>
      <label>
        {t('导入模式')}
        <Select
          aria-label={t('导入模式')}
          value={mode}
          options={[
            { value: 'append', label: t('追加（跳过重复题目）') },
            { value: 'overwrite', label: t('整库替换（清空后导入）') },
          ]}
          onChange={(value: ImportMode) => setMode(value)}
        />
      </label>
      <Button
        type="primary"
        aria-label={t('开始导入')}
        disabled={
          !canSubmitImport(file !== null, busy, progress?.status ?? null)
        }
        onClick={submit}
      >
        {busy ? t('导入中…') : t('开始导入')}
      </Button>
      <Button aria-label={t('关闭导入面板')} disabled={busy} onClick={onClose}>
        {t('收起')}
      </Button>
      {progress && !isImportTerminalStatus(progress.status) && (
        <p role="status">
          {importStatusLabel(progress.status)} · {progress.processed} /{' '}
          {progress.total || '…'}（{Math.round(progress.percentage)}%）
          {progress.status === 'paused' &&
            t(
              '导入已暂停；此页面不支持恢复或取消。请勿重复提交，持续暂停时联系管理员并提供导入任务 ID：{{jobId}}。',
              { jobId: progress.job_id },
            )}
        </p>
      )}
      {report && <ValidationReport report={report} />}
    </div>
  )
}

function HistoryDrawer({
  problem,
  onClose,
}: {
  problem: ProblemOption | null
  onClose: () => void
}) {
  useTranslation()

  const { client } = useProblemSession()
  const [offset, setOffset] = useState(0)
  // 抽屉关闭（problem=null）时不发请求：短路 owner 阻止 useList 取数
  const load = useCallback(
    (query: { limit: number; offset: number }, signal: AbortSignal) =>
      client.problemHistory(problem?.problem_id ?? '', query, signal),
    [client, problem],
  )
  const query = useMemo<ProblemListQuery & { source: 'all' }>(
    () => ({ source: 'all', limit: 20, offset }),
    [offset],
  )
  const list = useList<ProblemHistoryItem>(load, query, problem ? 'owner' : '')
  const data = list.data as ApiPage<ProblemHistoryItem> | undefined
  const items = data?.items ?? []
  const passed = items.filter((item) => item.status === 'passed').length
  return (
    <Drawer
      title={
        problem
          ? t('{{value1}} · 评估历史', {
              value1: problem.title || problem.problem_id,
            })
          : ''
      }
      open={!!problem}
      onClose={onClose}
      width={560}
    >
      {list.status === 'loading' ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : list.status === 'error' ? (
        <ExperimentFeedback
          message={t(list.error ?? t('加载失败'))}
          retry={list.reload}
        />
      ) : items.length ? (
        <>
          <p role="status">
            {t('本页 ')}
            {items.length} {t(' 条 · 通过 ')}
            {passed} {t(' · 通过率')} {formatRate(passed, items.length)}
          </p>
          <table
            className="evaluation-list-table"
            aria-label={t('题目评估历史')}
          >
            <thead>
              <tr>
                {[
                  t('策略'),
                  t('状态'),
                  t('迭代'),
                  'token',
                  t('耗时(s)'),
                  t('运行'),
                ].map((name) => (
                  <th key={name} scope="col">
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index}>
                  <td>{item.strategy}</td>
                  <td>{historyStatusLabel(item.status)}</td>
                  <td>{item.iterations ?? '—'}</td>
                  <td>{item.tokens ?? '—'}</td>
                  <td>{item.execution_time ?? '—'}</td>
                  <td>{item.run_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav className="evaluation-pagination" aria-label={t('历史分页')}>
            <Button disabled={offset === 0} onClick={() => setOffset(0)}>
              {t('首页')}
            </Button>
            <Button
              disabled={!data?.has_more}
              onClick={() => setOffset(offset + 20)}
            >
              {t('下一页')}
            </Button>
          </nav>
        </>
      ) : (
        <p role="status">{t('该题还没有评估记录。')}</p>
      )}
    </Drawer>
  )
}

export default function ProblemsPage() {
  useTranslation()

  const { client, owner } = useProblemSession()
  const [search, setSearch] = useSearchParams()
  const rawSearch = search.toString()
  const listSearch = new URLSearchParams(rawSearch)
  listSearch.delete('import')
  const rawListSearch = listSearch.toString()
  const query = useMemo(
    () => readListQuery(new URLSearchParams(rawListSearch)),
    [rawListSearch],
  )
  const importOpen = search.get('import') === '1'
  const [historyProblem, setHistoryProblem] = useState<ProblemOption | null>(
    null,
  )
  const [sources, setSources] = useState<
    { id: string; label: string; problem_count: number }[]
  >([])
  const [exportBusy, setExportBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void client
      .options(controller.signal)
      .then((meta) => {
        if (!controller.signal.aborted) setSources(meta.sources)
      })
      .catch(() => {
        // 计数徽标失败不阻塞列表
      })
    return () => controller.abort()
  }, [client])

  const load = useCallback(
    (listQuery: { limit: number; offset: number }, signal: AbortSignal) =>
      client.problems({ ...query, ...listQuery }, signal),
    [client, query],
  )
  const list = useList<ProblemOption>(load, query, owner ?? '')
  const data = list.data

  function exportLibrary(format: 'json' | 'csv') {
    if (exportBusy) return
    setExportBusy(true)
    window.open(client.exportUrl(format), '_blank')
    setTimeout(() => setExportBusy(false), 500)
  }

  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('题目库')}</h1>
          <p>{t('浏览共享与个人题目，导入与管理个人题库。')}</p>
        </div>
        <div className="evaluation-section-heading">
          <Select
            aria-label={t('导出格式')}
            value={undefined}
            placeholder={t('导出个人题库')}
            options={[
              { value: 'json', label: t('导出 JSON') },
              { value: 'csv', label: t('导出 CSV') },
            ]}
            onChange={(value: 'json' | 'csv') => exportLibrary(value)}
          />
          <Button
            type="primary"
            aria-label={t('导入题目')}
            onClick={() => setSearch(setProblemImportIntent(search, true))}
          >
            {t('导入题目')}
          </Button>
        </div>
      </header>
      <div className="panel evaluation-panel">
        <div className="evaluation-section-heading">
          <Select
            aria-label={t('题目来源')}
            value={query.source}
            options={[
              { value: 'all', label: t('全部来源') },
              ...sources.map((source) => ({
                value: source.id,
                label: `${source.label}（${source.problem_count}）`,
              })),
            ]}
            onChange={(source: string) =>
              setSearch(
                writeProblemListQuery(
                  {
                    source: source as ProblemListQuery['source'],
                    limit: query.limit,
                    offset: 0,
                  },
                  search,
                ),
              )
            }
          />
          {data && list.status !== 'loading' && (
            <span role="status">
              {t('共 ')}
              {data.total} {t(' 道题目')}
            </span>
          )}
        </div>
        <div hidden={!importOpen}>
          <ImportPanel
            onImported={list.reload}
            onClose={() =>
              setSearch(setProblemImportIntent(search, false), {
                replace: true,
              })
            }
          />
        </div>
        {list.status === 'loading' ? (
          <div aria-busy="true">
            <p role="status">{t('正在加载题目…')}</p>
            <Skeleton active paragraph={{ rows: 5 }} />
          </div>
        ) : list.status === 'error' ? (
          <ExperimentFeedback
            message={t(list.error ?? t('加载失败，请重试'))}
            retry={list.reload}
          />
        ) : data?.items.length ? (
          <table className="evaluation-list-table" aria-label={t('题目列表')}>
            <thead>
              <tr>
                {[t('题目 ID / 标题'), t('难度'), t('来源'), t('操作')].map(
                  (name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data.items.map((problem) => (
                <tr key={problem.problem_id}>
                  <td>
                    {problem.title || problem.problem_id}
                    <small>{problem.problem_id}</small>
                  </td>
                  <td>{difficultyLabel(problem.difficulty)}</td>
                  <td>{sourceLabel(problem.source)}</td>
                  <td>
                    <Button
                      size="small"
                      onClick={() => setHistoryProblem(problem)}
                    >
                      {t('评估历史')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p role="status">{t('当前来源没有题目。')}</p>
        )}
        {data && list.status !== 'loading' && (
          <nav className="evaluation-pagination" aria-label={t('题目分页')}>
            <span>
              {data.total
                ? `${data.offset + 1}–${data.offset + data.items.length} / ${data.total}`
                : '0 / 0'}
            </span>
            <Button
              aria-label={t('上一页题目')}
              disabled={query.offset === 0}
              onClick={() =>
                setSearch(
                  writeProblemListQuery(
                    {
                      ...query,
                      offset: Math.max(0, query.offset - query.limit),
                    },
                    search,
                  ),
                )
              }
            >
              {t('上一页')}
            </Button>
            <Button
              aria-label={t('下一页题目')}
              disabled={!data.has_more}
              onClick={() =>
                setSearch(
                  writeProblemListQuery(
                    { ...query, offset: query.offset + query.limit },
                    search,
                  ),
                )
              }
            >
              {t('下一页')}
            </Button>
          </nav>
        )}
      </div>
      <HistoryDrawer
        problem={historyProblem}
        onClose={() => setHistoryProblem(null)}
      />
    </section>
  )
}
