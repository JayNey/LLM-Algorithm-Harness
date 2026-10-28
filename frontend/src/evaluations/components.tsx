import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
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
  useTranslation()

  return (
    <Alert
      type="error"
      showIcon
      title={message}
      action={retry ? <Button onClick={retry}>{t('重试')}</Button> : undefined}
    />
  )
}

export function EvaluationFacts({ evaluation }: { evaluation: Evaluation }) {
  useTranslation()

  const progress = evaluation.execution_progress
  return (
    <>
      <dl className="evaluation-facts">
        <div>
          <dt>{t('状态')}</dt>
          <dd>{evaluationLabel(evaluation)}</dd>
        </div>
        <div>
          <dt>{t('模型')}</dt>
          <dd>{evaluation.model ?? t('未知')}</dd>
        </div>
        <div>
          <dt>{t('策略')}</dt>
          <dd>{evaluation.strategy_names.join('、') || t('未知')}</dd>
        </div>
        <div>
          <dt>{t('题目数')}</dt>
          <dd>{evaluation.problem_count}</dd>
        </div>
        <div>
          <dt>{t('已花费')}</dt>
          <dd>{metricLabel(evaluation.spent_usd, 'USD')}</dd>
        </div>
        <div>
          <dt>{t('预算上限')}</dt>
          <dd>
            {evaluation.budget_cap_usd === null
              ? t('未设置上限')
              : metricLabel(evaluation.budget_cap_usd, 'USD')}
          </dd>
        </div>
        <div>
          <dt>{t('执行进度')}</dt>
          <dd>
            {progress.completed_units} / {progress.total_units} {t(' 单元（')}
            {progress.percentage}%）
          </dd>
        </div>
        <div>
          <dt>{t('创建时间')}</dt>
          <dd>{evaluation.created_at}</dd>
        </div>
        <div>
          <dt>{t('更新时间')}</dt>
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
  useTranslation()

  return (
    <>
      <h2>{t('策略汇总')}</h2>
      <p>{t('全量已记录单元的统计，不随下方单题分页变化。')}</p>
      {result.strategies.length ? (
        <div
          className="evaluation-list-scroll"
          role="region"
          aria-label={t('可滚动的策略汇总')}
          tabIndex={0}
        >
          <table className="evaluation-list-table" aria-label={t('策略汇总')}>
            <thead>
              <tr>
                {[
                  t('策略'),
                  t('成功 / 记录单元'),
                  t('成功率'),
                  t('平均 Token'),
                  t('平均执行耗时'),
                  t('估算费用'),
                  t('难度分布'),
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
                  <td>{metricLabel(strategy.avg_execution_time, t('秒'))}</td>
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
        <p>{t('尚无策略统计')}</p>
      )}
      <h2>{t('单题结果')}</h2>
      {result.problems.items.length ? (
        <div
          className="evaluation-list-scroll"
          role="region"
          aria-label={t('可滚动的单题结果')}
          tabIndex={0}
        >
          <table className="evaluation-list-table" aria-label={t('单题结果')}>
            <thead>
              <tr>
                {[
                  t('题目 ID'),
                  t('策略'),
                  t('单元状态'),
                  t('迭代次数'),
                  'Token',
                  t('执行耗时'),
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
                  <td>{metricLabel(row.execution_time, t('秒'))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>{t('当前页没有单题记录')}</p>
      )}
    </>
  )
}
