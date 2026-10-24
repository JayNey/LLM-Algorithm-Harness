import { Alert, Button, Skeleton } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiClientError } from '@/auth/http.ts'
import { formatDateTime } from '@/benchmarks/presentation.ts'
import { SuiteForm } from '@/benchmarks/SuiteForm.tsx'
import { useBenchmarkSession } from '@/benchmarks/session.tsx'
import type {
  BenchmarkSuite,
  SuiteDraft,
  SuiteDraftErrors,
} from '@/benchmarks/types.ts'
import {
  suiteCreateInput,
  validateSuiteDraft,
} from '@/benchmarks/validation.ts'
import '@/evaluations/workflow.css'

function emptyDraft(): SuiteDraft {
  return {
    name: '',
    version: '1.0',
    description: '',
    frozen: false,
    problems_text: '',
  }
}

function useSuites() {
  const { client, owner } = useBenchmarkSession()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{
    owner: string | null
    attempt: number
    data?: BenchmarkSuite[]
    error?: string
  }>()
  useEffect(() => {
    if (!owner) return
    const controller = new AbortController()
    void client.suites(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ owner, attempt, data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            owner,
            attempt,
            error:
              error instanceof ApiClientError
                ? error.message
                : '加载失败，请重试',
          })
      },
    )
    return () => controller.abort()
  }, [client, owner, attempt])
  const current = !!owner && state?.owner === owner && state.attempt === attempt
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !current,
    reload: () => setAttempt((value) => value + 1),
  }
}

export default function BenchmarksPage() {
  const { client } = useBenchmarkSession()
  const suites = useSuites()
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<SuiteDraft>(emptyDraft)
  const [errors, setErrors] = useState<SuiteDraftErrors>({})
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const submit = useCallback(async () => {
    const nextErrors = validateSuiteDraft(draft)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    setActionError(null)
    try {
      await client.createSuite(suiteCreateInput(draft))
      setCreating(false)
      setDraft(emptyDraft())
      suites.reload()
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '创建失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }, [client, draft, suites])
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>基准测试</h1>
          <p>固定题集套件：重复运行并追踪模型的学习曲线。</p>
        </div>
        {!creating && (
          <Button
            type="primary"
            aria-label="新建套件"
            onClick={() => setCreating(true)}
          >
            新建套件
          </Button>
        )}
      </header>
      {actionError && <Alert role="alert" type="error" message={actionError} />}
      {creating && (
        <SuiteForm
          draft={draft}
          errors={errors}
          onChange={(patch) =>
            setDraft((previous) => ({ ...previous, ...patch }))
          }
          onSubmit={() => void submit()}
          onCancel={() => {
            setCreating(false)
            setErrors({})
          }}
          busy={busy}
          submitLabel="创建套件"
        />
      )}
      <div className="panel evaluation-panel">
        {suites.loading ? (
          <div aria-busy="true">
            <p role="status">正在加载套件…</p>
            <Skeleton active paragraph={{ rows: 4 }} />
          </div>
        ) : suites.error ? (
          <Alert
            role="alert"
            type="error"
            message={suites.error}
            action={<Button onClick={suites.reload}>重试</Button>}
          />
        ) : suites.data?.length ? (
          <table className="evaluation-list-table" aria-label="基准套件列表">
            <thead>
              <tr>
                {['名称 / 版本', '题目数', '状态', '更新时间'].map((name) => (
                  <th key={name} scope="col">
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {suites.data.map((suite) => (
                <tr key={suite.id}>
                  <td>
                    <Link to={`/benchmarks/${encodeURIComponent(suite.id)}`}>
                      {suite.name}
                    </Link>
                    <small>v{suite.version}</small>
                  </td>
                  <td>{suite.problems.length}</td>
                  <td>{suite.frozen ? '已冻结' : '可编辑'}</td>
                  <td>
                    <time dateTime={suite.updated_at}>
                      {formatDateTime(suite.updated_at)}
                    </time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p role="status">还没有基准套件，点击「新建套件」开始。</p>
        )}
      </div>
    </section>
  )
}
