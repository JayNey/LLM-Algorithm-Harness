import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import {
  Alert,
  Button,
  Drawer,
  Input,
  Select,
  Skeleton,
  Space,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiClientError } from '@/auth/http.ts'
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
  ImportJobProgress,
  ImportMode,
  ImportValidation,
  LeetCodeImportResult,
  PersonalProblemDetail,
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
import { useAuthStore } from '@/store/auth.ts'
import { GovernancePanel } from './GovernancePanel.tsx'
import {
  LeetCodeBatchImport,
  type BatchOutcome,
} from './LeetCodeBatchImport.tsx'

const IMPORT_POLL_MS = 3_000
const LEETCODE_ERRORS: Partial<Record<number, string>> = {
  400: '请输入 LeetCode 国际站的公开题目链接。',
  404: 'LeetCode 题目不存在或无法公开访问。',
  408: 'LeetCode 请求超时，请重试。',
  429: '导入请求过多，请稍后重试。',
  503: '暂时无法连接 LeetCode，请稍后重试。',
}

function readImportJob(storageKey: string): string | null {
  try {
    return localStorage.getItem(storageKey) || null
  } catch {
    return null
  }
}

function rememberImportJob(storageKey: string, jobId: string) {
  try {
    localStorage.setItem(storageKey, jobId)
  } catch {
    // 当前页面仍可查询作业，即使浏览器禁用了存储。
  }
}

function forgetImportJob(storageKey: string, jobId: string) {
  try {
    if (localStorage.getItem(storageKey) === jobId)
      localStorage.removeItem(storageKey)
  } catch {
    // 浏览器拒绝访问存储时仍然展示终态。
  }
}

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
  onOpenProblem,
  onClose,
}: {
  onImported: () => void
  onOpenProblem: (problemId: string) => void
  onClose: () => void
}) {
  useTranslation()

  const { client, owner } = useProblemSession()
  const storageKey = `llm-harness-problem-import:session:${owner}`
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [mode, setMode] = useState<ImportMode>('append')
  const [busy, setBusy] = useState<'file' | 'leetcode' | 'batch' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [leetcodeError, setLeetcodeError] = useState<string | null>(null)
  const [batchError, setBatchError] = useState<string | null>(null)
  const [batchOutcomes, setBatchOutcomes] = useState<
    Record<string, BatchOutcome>
  >({})
  const [report, setReport] = useState<ImportValidation | null>(null)
  const [leetcodeResult, setLeetcodeResult] =
    useState<LeetCodeImportResult | null>(null)
  const [jobId, setJobId] = useState(() => readImportJob(storageKey))
  const [progress, setProgress] = useState<ImportJobProgress | null>(null)
  const [pollPaused, setPollPaused] = useState(false)
  const submitLock = useRef(false)

  useEffect(() => {
    if (!jobId || pollPaused) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0
    let imported = 0
    const stillCurrent = () =>
      !controller.signal.aborted &&
      useAuthStore.getState().session?.marker === owner

    async function poll(id: string) {
      if (!stillCurrent()) return
      let next: ImportJobProgress
      try {
        next = await client.importJob(id, controller.signal)
      } catch {
        if (!stillCurrent()) return
        failures += 1
        if (failures >= 3) setPollPaused(true)
        else timer = setTimeout(() => void poll(id), IMPORT_POLL_MS)
        return
      }
      if (!stillCurrent()) return
      failures = 0
      setProgress(next)
      if (next.batch) {
        const finished = next.batch.items
          .filter((item) => item.status !== 'pending')
          .map((item) => [item.slug, { ...item, jobId: next.job_id }] as const)
        setBatchOutcomes((previous) => ({
          ...previous,
          ...Object.fromEntries(finished),
        }))
        if (next.batch.imported > imported) {
          imported = next.batch.imported
          onImported()
        }
      }
      if (!isImportTerminalStatus(next.status)) {
        timer = setTimeout(() => void poll(id), IMPORT_POLL_MS)
        return
      }

      forgetImportJob(storageKey, id)
      setJobId(null)
      submitLock.current = false
      if (next.status === 'completed' && !next.batch) {
        setReport(next.result)
        onImported()
      } else if (next.status === 'failed') {
        if (next.batch) {
          setBatchError('LeetCode 批量导入任务失败，请重试。')
        } else {
          setError(
            next.failureDetail
              ? t('导入任务失败：{{value1}}', { value1: next.failureDetail })
              : '导入任务失败，请检查文件格式后重试。',
          )
        }
      }
    }
    timer = setTimeout(() => void poll(jobId), 0)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [client, jobId, onImported, owner, pollPaused, storageKey])

  async function submit(
    request: 'file' | 'leetcode' | { slugs: string[]; retryJobId?: string },
  ) {
    const kind = typeof request === 'string' ? request : 'batch'
    const selectedFile = file
    const selectedUrl = url.trim()
    const sameSession = () => useAuthStore.getState().session?.marker === owner
    if (
      !owner ||
      !sameSession() ||
      !canSubmitImport(
        typeof request !== 'string'
          ? request.slugs.length > 0
          : kind === 'file'
            ? selectedFile !== null
            : !!selectedUrl,
        busy !== null,
        progress?.status ?? null,
        submitLock.current || jobId !== null,
      )
    )
      return
    const savedJob = readImportJob(storageKey)
    if (savedJob) {
      setJobId(savedJob)
      setError(null)
      setLeetcodeError(null)
      setBatchError(null)
      setReport(null)
      setLeetcodeResult(null)
      setProgress(null)
      return
    }
    if (kind === 'file' && selectedFile) {
      const fileError = validateImportFile(selectedFile)
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
    }
    submitLock.current = true
    setBusy(kind)
    setError(null)
    setLeetcodeError(null)
    setBatchError(null)
    setReport(null)
    setLeetcodeResult(null)
    setProgress(null)
    let startedJob = false
    try {
      if (typeof request !== 'string') {
        const started = request.retryJobId
          ? await client.retryLeetCodeBatch(request.retryJobId, request.slugs)
          : await client.startLeetCodeBatch(request.slugs)
        if (!sameSession()) return
        if (!request.retryJobId) setBatchOutcomes({})
        rememberImportJob(storageKey, started.job_id)
        startedJob = true
        setJobId(started.job_id)
      } else if (kind === 'leetcode') {
        const result = await client.importLeetCode(selectedUrl)
        if (!sameSession()) return
        setLeetcodeResult(result)
        if (result.imported) onImported()
      } else if (selectedFile && selectedFile.size <= DIRECT_IMPORT_MAX_BYTES) {
        const result = await client.directImport(selectedFile, mode)
        if (!sameSession()) return
        setReport(result.validation)
        onImported()
      } else if (selectedFile) {
        const uploaded = await client.uploadFile(selectedFile)
        if (!sameSession()) return
        const started = await client.startImport(uploaded.file_id, mode)
        if (!sameSession()) return
        rememberImportJob(storageKey, started.job_id)
        startedJob = true
        setJobId(started.job_id)
      }
    } catch (cause) {
      if (sameSession()) {
        const message =
          kind === 'leetcode' && cause instanceof ApiClientError
            ? LEETCODE_ERRORS[cause.status ?? 0]
            : undefined
        const fallback =
          cause instanceof Error ? cause.message : '导入失败，请重试'
        if (kind === 'batch') setBatchError(fallback)
        else if (kind === 'leetcode') setLeetcodeError(message ?? fallback)
        else setError(fallback)
      }
    } finally {
      if (!startedJob) submitLock.current = false
      setBusy(null)
    }
  }

  return (
    <div className="panel evaluation-panel" aria-label={t('题目导入')}>
      <h3>{t('导入题目（个人题库）')}</h3>
      <p>
        {t('支持 JSON / CSV 文件；小于 5MiB 直接导入，大文件转入后台任务。')}
      </p>
      {error && <Alert role="alert" type="error" message={t(error)} />}
      {pollPaused && (
        <Alert
          role="alert"
          type="warning"
          message={t('进度查询连续失败，可以重试查询原导入作业。')}
          action={
            <Button onClick={() => setPollPaused(false)}>
              {t('重试查询导入进度')}
            </Button>
          }
        />
      )}
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
          !canSubmitImport(
            file !== null,
            busy !== null,
            progress?.status ?? null,
            jobId !== null,
          )
        }
        onClick={() => void submit('file')}
      >
        {busy === 'file' ? t('导入中…') : t('开始导入')}
      </Button>
      <Button
        aria-label={t('关闭导入面板')}
        disabled={busy !== null}
        onClick={onClose}
      >
        {t('收起')}
      </Button>
      {jobId && !progress && !pollPaused && (
        <p role="status">{t('正在查询导入进度…')}</p>
      )}
      {progress && (
        <p role="status">
          {importStatusLabel(progress.status)}
          {!isImportTerminalStatus(progress.status) &&
            ` · ${progress.processed} / ${progress.total || '…'}（${Math.round(progress.percentage)}%）`}
          {progress.status === 'paused' &&
            t(
              '导入已暂停；此页面不支持恢复或取消。请勿重复提交，持续暂停时联系管理员并提供导入任务 ID：{{jobId}}。',
              { jobId: progress.job_id },
            )}
        </p>
      )}
      {report && <ValidationReport report={report} />}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit('leetcode')
        }}
      >
        <h4>{t('从 LeetCode 导入')}</h4>
        <p>{t('粘贴 LeetCode 国际站的一道公开题目链接。')}</p>
        <Space.Compact block>
          <Input
            aria-label={t('LeetCode 题目链接')}
            placeholder="https://leetcode.com/problems/two-sum/"
            maxLength={1000}
            value={url}
            disabled={busy === 'leetcode'}
            onChange={(event) => setUrl(event.target.value)}
          />
          <Button
            htmlType="submit"
            loading={busy === 'leetcode'}
            disabled={
              !canSubmitImport(
                !!url.trim(),
                busy !== null,
                progress?.status ?? null,
                jobId !== null,
              )
            }
          >
            {t('导入链接')}
          </Button>
        </Space.Compact>
        {leetcodeError && (
          <Alert role="alert" type="error" title={t(leetcodeError)} />
        )}
        {busy === 'leetcode' && (
          <p role="status">{t('正在从 LeetCode 导入…')}</p>
        )}
        {leetcodeResult && (
          <p role="status">
            {t(
              leetcodeResult.imported
                ? '已导入个人题库。'
                : '题目已存在，已跳过。',
            )}
            <Button
              type="link"
              onClick={() => onOpenProblem(leetcodeResult.problem_id)}
            >
              {t('查看题目')}
            </Button>
          </p>
        )}
      </form>
      <LeetCodeBatchImport
        client={client}
        blocked={
          !canSubmitImport(
            true,
            busy !== null,
            progress?.status ?? null,
            jobId !== null,
          )
        }
        submitting={busy === 'batch'}
        submitError={batchError}
        outcomes={Object.values(batchOutcomes)}
        onSubmit={(slugs, retryJobId) => void submit({ slugs, retryJobId })}
      />
    </div>
  )
}

type DetailTarget = Pick<ProblemOption, 'problem_id' | 'title'>

function PersonalDetail({ problemId }: { problemId: string }) {
  useTranslation()
  const { client } = useProblemSession()
  const [detail, setDetail] = useState<PersonalProblemDetail | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void client.personalProblem(problemId, controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) setDetail(result)
      },
      () => {
        if (!controller.signal.aborted) setFailed(true)
      },
    )
    return () => controller.abort()
  }, [attempt, client, problemId])

  if (failed)
    return (
      <ExperimentFeedback
        message={t('题目详情加载失败')}
        retry={() => {
          setFailed(false)
          setAttempt((value) => value + 1)
        }}
      />
    )
  if (!detail) return <p role="status">{t('正在加载题目…')}</p>
  return (
    <>
      {detail.source_url && (
        <p>
          <a href={detail.source_url} target="_blank" rel="noopener noreferrer">
            {t('在 LeetCode 查看原题')}
          </a>
        </p>
      )}
      {detail.needs_manual_completion && (
        <Alert type="info" title={t('公开样例或 Python 入口需人工补全。')} />
      )}
      <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
        {detail.description}
      </p>
    </>
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
      {problem && (
        <ProblemHistory
          key={problem.problem_id}
          problemId={problem.problem_id}
        />
      )}
    </Drawer>
  )
}

function ProblemHistory({ problemId }: { problemId: string }) {
  useTranslation()

  const { client } = useProblemSession()
  const [offset, setOffset] = useState(0)
  const load = useCallback(
    (query: { limit: number; offset: number }, signal: AbortSignal) =>
      client.problemHistory(problemId, query, signal),
    [client, problemId],
  )
  const query = useMemo<ProblemListQuery & { source: 'all' }>(
    () => ({ source: 'all', limit: 20, offset }),
    [offset],
  )
  const list = useList<ProblemHistoryItem>(load, query, problemId)
  const data = list.data as ApiPage<ProblemHistoryItem> | undefined
  const items = data?.items ?? []
  const passed = items.filter((item) => item.status === 'success').length
  const evaluated = items.filter(
    (item) => item.status !== 'not_evaluable',
  ).length
  return (
    <>
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
            {passed} {t(' · 通过率')} {formatRate(passed, evaluated)}
          </p>
          <div className="evaluation-list-scroll">
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
          </div>
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
    </>
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
  const [governanceOpen, setGovernanceOpen] = useState(false)
  const [historyProblem, setHistoryProblem] = useState<ProblemOption | null>(
    null,
  )
  const [detailProblem, setDetailProblem] = useState<DetailTarget | null>(null)
  const [sources, setSources] = useState<
    { id: string; label: string; problem_count: number }[]
  >([])
  const [exportBusy, setExportBusy] = useState(false)
  const [exportError, setExportError] = useState(false)
  const exportPending = useRef(false)
  const [sourcesVersion, setSourcesVersion] = useState(0)

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
  }, [client, sourcesVersion])

  const load = useCallback(
    (listQuery: { limit: number; offset: number }, signal: AbortSignal) =>
      client.problems({ ...query, ...listQuery }, signal),
    [client, query],
  )
  const list = useList<ProblemOption>(load, query, owner ?? '')
  const { reload } = list
  const onImported = useCallback(() => {
    reload()
    setSourcesVersion((version) => version + 1)
  }, [reload])
  const data = list.data

  async function exportLibrary(format: 'json' | 'csv') {
    if (exportPending.current) return
    exportPending.current = true
    setExportBusy(true)
    setExportError(false)
    try {
      const blob = await client.exportLibrary(format)
      if (useAuthStore.getState().session?.marker !== owner) return
      if (!(blob instanceof Blob)) {
        setExportError(true)
        return
      }
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      try {
        link.href = url
        link.download = `problems.${format}`
        document.body.append(link)
        link.click()
      } finally {
        link.remove()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch {
      if (useAuthStore.getState().session?.marker === owner)
        setExportError(true)
    } finally {
      exportPending.current = false
      setExportBusy(false)
    }
  }

  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('题目库')}</h1>
          <p>{t('浏览共享与个人题目，导入与管理个人题库。')}</p>
        </div>
        <div className="evaluation-section-heading">
          <Button onClick={() => setGovernanceOpen(true)}>
            {t('批量治理')}
          </Button>
          <Select
            aria-label={t('导出格式')}
            value={undefined}
            placeholder={t('导出个人题库')}
            loading={exportBusy}
            disabled={exportBusy}
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
      {exportError && (
        <Alert role="alert" type="error" message={t('操作失败，请重试')} />
      )}
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
            onImported={onImported}
            onOpenProblem={(problemId) =>
              setDetailProblem({ problem_id: problemId, title: problemId })
            }
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
          <div className="evaluation-list-scroll">
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
                      <Space wrap size="small">
                        {problem.source === 'personal' && (
                          <Button
                            size="small"
                            onClick={() => setDetailProblem(problem)}
                          >
                            {t('题目详情')}
                          </Button>
                        )}
                        <Button
                          size="small"
                          onClick={() => setHistoryProblem(problem)}
                        >
                          {t('评估历史')}
                        </Button>
                      </Space>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
      <Drawer
        title={
          detailProblem
            ? t('题目详情：{{value1}}', { value1: detailProblem.title })
            : ''
        }
        open={!!detailProblem}
        onClose={() => setDetailProblem(null)}
        width={560}
      >
        {detailProblem && (
          <PersonalDetail
            key={detailProblem.problem_id}
            problemId={detailProblem.problem_id}
          />
        )}
      </Drawer>
      {governanceOpen && (
        <GovernancePanel onClose={() => setGovernanceOpen(false)} />
      )}
    </section>
  )
}
