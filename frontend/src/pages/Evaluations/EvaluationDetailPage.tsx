import { Alert, Button } from 'antd'
import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useStore } from 'zustand'
import {
  EvaluationFeedback,
  EvaluationFacts,
} from '@/evaluations/components.tsx'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import { useEvaluation } from '@/evaluations/useEvaluation.ts'
import '@/evaluations/workflow.css'

export default function EvaluationDetailPage() {
  const { evaluationId = '' } = useParams()
  const { owner, client, creationStore } = useEvaluationSession()
  const receipt = useStore(creationStore)
  const detail = useEvaluation(client, evaluationId, owner)
  const busy =
    ['creating', 'created', 'starting'].includes(receipt.phase) ||
    !!receipt.action?.pending
  const actionScope = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    actionScope.current = controller
    return () => {
      controller.abort()
      actionScope.current = null
    }
  }, [evaluationId, owner])
  const previous = useRef(busy)
  const { reload } = detail
  useEffect(() => {
    // Also refresh when the create page's automatic start finishes after navigation.
    if (previous.current && !busy) reload()
    previous.current = busy
  }, [busy, reload])
  const actionError =
    receipt.action?.evaluationId === evaluationId
      ? receipt.action.error
      : receipt.evaluationId === evaluationId
        ? receipt.error
        : null
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>评估任务详情</h1>
          <p>查看任务状态与费用，按当前支持的操作管理任务。</p>
        </div>
        <Link to="/evaluations">返回任务列表</Link>
      </header>
      <section
        className="panel evaluation-panel"
        aria-label="评估详情"
        aria-busy={detail.loading || busy}
      >
        <dl className="evaluation-receipt">
          <dt>任务 ID</dt>
          <dd>{evaluationId}</dd>
        </dl>
        {actionError && (
          <Alert
            showIcon
            type="warning"
            title={
              receipt.phase === 'start-error'
                ? '任务已创建，启动尚未确认'
                : '操作尚未确认'
            }
            description={`${actionError.message}。请核对最新任务状态后重试。`}
          />
        )}
        {detail.loading && <p role="status">正在加载评估详情…</p>}
        {detail.error && (
          <EvaluationFeedback
            message={
              detail.data
                ? `${detail.error}；下方为上次读取的数据，请刷新后操作。`
                : detail.error
            }
            retry={reload}
          />
        )}
        {detail.data && <EvaluationFacts evaluation={detail.data} />}
        <div className="evaluation-actions">
          <Button onClick={reload} disabled={detail.loading || busy}>
            刷新任务
          </Button>
          {detail.data?.can_start && (
            <Button
              type="primary"
              disabled={busy || detail.loading || !!detail.error}
              onClick={() => {
                if (actionScope.current)
                  void receipt.act(
                    evaluationId,
                    'start',
                    actionScope.current.signal,
                  )
              }}
            >
              启动任务
            </Button>
          )}
          {detail.data?.can_cancel && (
            <Button
              danger
              disabled={busy || detail.loading || !!detail.error}
              onClick={() => {
                if (actionScope.current)
                  void receipt.act(
                    evaluationId,
                    'cancel',
                    actionScope.current.signal,
                  )
              }}
            >
              取消任务
            </Button>
          )}
          {busy && <span role="status">正在等待操作响应…</span>}
        </div>
      </section>
    </section>
  )
}
