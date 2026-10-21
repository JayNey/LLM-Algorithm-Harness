import { Alert } from 'antd'
import { Link, useParams } from 'react-router-dom'
import { useStore } from 'zustand'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import '@/evaluations/workflow.css'

export default function EvaluationDetailPage() {
  const { evaluationId } = useParams()
  const { creationStore } = useEvaluationSession()
  const receipt = useStore(creationStore)
  const confirmed = !!evaluationId && receipt.evaluationId === evaluationId
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>评估任务</h1>
          <p>查看创建与启动回执。</p>
        </div>
        <Link to="/evaluations">返回任务列表</Link>
      </header>
      <div className="panel evaluation-panel">
        {confirmed ? (
          <>
            <dl className="evaluation-receipt">
              <dt>任务 ID</dt>
              <dd>{evaluationId}</dd>
            </dl>
            <Alert
              showIcon
              type={receipt.phase === 'start-error' ? 'warning' : 'info'}
              title={
                receipt.phase === 'start-error'
                  ? '任务已创建，启动尚未确认'
                  : receipt.phase === 'queued'
                    ? '启动请求已确认'
                    : '任务已创建，正在请求启动'
              }
              description={
                receipt.phase === 'start-error'
                  ? `${receipt.error?.message ?? '启动请求失败'}。请保留任务 ID，并在任务列表核对状态。`
                  : receipt.phase === 'queued'
                    ? '启动请求已被接受，实际执行状态请查看任务列表。'
                    : '请稍候，正在等待启动响应。'
              }
            />
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            title="当前没有可显示的创建回执"
            description="请返回任务列表核对该任务。"
          />
        )}
        <div className="evaluation-actions">
          <Link to="/evaluations">查看任务列表</Link>
        </div>
      </div>
    </section>
  )
}
