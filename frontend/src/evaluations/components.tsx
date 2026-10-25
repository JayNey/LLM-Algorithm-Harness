import type { Evaluation, ResultDetail } from './types.ts'
import {
  evaluationLabel,
  metricLabel,
  resultCostLabel,
  successRateLabel,
} from './presentation.ts'
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

export function ResultTables({ result }: { result: ResultDetail }) {
  return (
    <>
      <h2>策略汇总</h2>
      <p>全量已记录单元的统计，不随下方单题分页变化。</p>
      {result.strategies.length ? (
        <div
          className="evaluation-list-scroll"
          role="region"
          aria-label="可滚动的策略汇总"
          tabIndex={0}
        >
          <table className="evaluation-list-table" aria-label="策略汇总">
            <thead>
              <tr>
                {[
                  '策略',
                  '成功 / 记录单元',
                  '成功率',
                  '平均 Token',
                  '平均执行耗时',
                  '估算费用',
                  '难度分布',
                ].map((name) => (
                  <th scope="col" key={name}>
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.strategies.map((strategy) => (
                <tr key={strategy.name}>
                  <td>{strategy.name}</td>
                  <td>
                    {strategy.solved_problems} / {strategy.total_problems}
                  </td>
                  <td>{successRateLabel(strategy.success_rate)}</td>
                  <td>{metricLabel(strategy.avg_tokens)}</td>
                  <td>{metricLabel(strategy.avg_execution_time, '秒')}</td>
                  <td>{resultCostLabel(strategy)}</td>
                  <td>
                    {Object.entries(strategy.by_difficulty).map(
                      ([name, row]) => (
                        <div key={name}>
                          {name}：{row.solved} / {row.total}（
                          {successRateLabel(row.success_rate)}）
                        </div>
                      ),
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>尚无策略统计</p>
      )}
      <h2>单题结果</h2>
      {result.problems.items.length ? (
        <div
          className="evaluation-list-scroll"
          role="region"
          aria-label="可滚动的单题结果"
          tabIndex={0}
        >
          <table className="evaluation-list-table" aria-label="单题结果">
            <thead>
              <tr>
                {[
                  '题目 ID',
                  '策略',
                  '单元状态',
                  '迭代次数',
                  'Token',
                  '执行耗时',
                ].map((name) => (
                  <th scope="col" key={name}>
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.problems.items.map((row) => (
                <tr key={JSON.stringify([row.problem_id, row.strategy])}>
                  <td>{row.problem_id}</td>
                  <td>{row.strategy}</td>
                  <td>{row.status}</td>
                  <td>{metricLabel(row.iterations)}</td>
                  <td>{metricLabel(row.tokens)}</td>
                  <td>{metricLabel(row.execution_time, '秒')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>当前页没有单题记录</p>
      )}
    </>
  )
}
