import type { Evaluation } from './types.ts'
import { evaluationLabel, metricLabel } from './presentation.ts'
import { Alert, Button } from 'antd'

export function EvaluationFeedback({
  message,
  retry,
}: {
  message: string
  retry?: () => void
}) {
  return (
    <Alert
      type="error"
      showIcon
      title={message}
      action={retry ? <Button onClick={retry}>重试</Button> : undefined}
    />
  )
}

export function EvaluationFacts({ evaluation }: { evaluation: Evaluation }) {
  const progress = evaluation.execution_progress
  return (
    <>
      <dl className="evaluation-facts">
        <div>
          <dt>状态</dt>
          <dd>{evaluationLabel(evaluation)}</dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd>{evaluation.model ?? '未知'}</dd>
        </div>
        <div>
          <dt>策略</dt>
          <dd>{evaluation.strategy_names.join('、') || '未知'}</dd>
        </div>
        <div>
          <dt>题目数</dt>
          <dd>{evaluation.problem_count}</dd>
        </div>
        <div>
          <dt>已花费</dt>
          <dd>{metricLabel(evaluation.spent_usd, 'USD')}</dd>
        </div>
        <div>
          <dt>预算上限</dt>
          <dd>
            {evaluation.budget_cap_usd === null
              ? '未设置上限'
              : metricLabel(evaluation.budget_cap_usd, 'USD')}
          </dd>
        </div>
        <div>
          <dt>执行进度</dt>
          <dd>
            {progress.completed_units} / {progress.total_units} 单元（
            {progress.percentage}%）
          </dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>{evaluation.created_at}</dd>
        </div>
        <div>
          <dt>更新时间</dt>
          <dd>{evaluation.updated_at}</dd>
        </div>
      </dl>
      {evaluation.error_message && (
        <p className="evaluation-reason">{evaluation.error_message}</p>
      )}
    </>
  )
}
