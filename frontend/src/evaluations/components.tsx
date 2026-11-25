import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import type { Evaluation, ResultDetail } from './types.ts'
import {
  resultStatusLabel,
  evaluationLabel,
  failureDiagnosticLabel,
  metricLabel,
  resultCostLabel,
  successRateLabel,
} from './presentation.ts'
import { Alert, Button } from 'antd'
import { Link } from 'react-router-dom'

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
  const knownCost =
    evaluation.known_cost_usd === undefined
      ? evaluation.spent_usd
      : evaluation.known_cost_usd
  const budgetLabels: Record<string, string> = {
    unlimited: t('未设置上限'),
    within_limit: t('预算内'),
    reached: t('已达预算上限'),
    missing_pricing: t('缺少模型定价'),
    unknown_cost: t('有费用无法核算'),
  }
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
        {evaluation.generation_timeout_seconds !== undefined && (
          <div>
            <dt>{t('模型生成超时')}</dt>
            <dd>
              {metricLabel(evaluation.generation_timeout_seconds, t('秒'))}
            </dd>
          </div>
        )}
        <div>
          <dt>{t('策略')}</dt>
          <dd>{evaluation.strategy_names.join('、') || t('未知')}</dd>
        </div>
        <div>
          <dt>{t('题目数')}</dt>
          <dd>{evaluation.problem_count}</dd>
        </div>
        <div>
          <dt>
            {t(evaluation.reuse_history ? '本次新增费用' : '已知费用合计')}
          </dt>
          <dd>
            {knownCost === null ? t('费用未知') : metricLabel(knownCost, 'USD')}
          </dd>
        </div>
        {evaluation.reuse_history && (
          <div>
            <dt>{t('复用 / 新跑单元')}</dt>
            <dd>
              {evaluation.reused_units ?? 0} / {evaluation.new_units ?? 0}
            </dd>
          </div>
        )}
        {evaluation.unknown_cost_count !== undefined && (
          <div>
            <dt>{t('费用未知单元')}</dt>
            <dd>{evaluation.unknown_cost_count}</dd>
          </div>
        )}
        {evaluation.budget_status && (
          <div>
            <dt>{t('预算状态')}</dt>
            <dd>
              {budgetLabels[evaluation.budget_status] ??
                evaluation.budget_status}
            </dd>
          </div>
        )}
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
      {result.reuse && (
        <div className="panel evaluation-panel" aria-label={t('增量运行汇总')}>
          <p>
            {t('复用 {{reused}}，新跑 {{fresh}}，共 {{total}} 个单元', {
              reused: result.reuse.reused_units,
              fresh: result.reuse.new_units,
              total: result.reuse.total_units,
            })}
          </p>
          <p>
            {t('本次新增费用')}：{metricLabel(result.reuse.new_cost_usd, 'USD')}
            {!!result.reuse.new_cost_unknown_count &&
              ` · ${t('费用未知单元')} ${result.reuse.new_cost_unknown_count}`}
          </p>
          {!!result.reuse.reused_units && (
            <p>
              {t(
                '策略费用与单元原始费用包含历史度量，本次预算只结算新增调用。',
              )}
            </p>
          )}
        </div>
      )}
      <h2>{t('策略汇总')}</h2>
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
                  t('成功 / 已评估单元'),
                  t('成功率'),
                  t('平均 Token'),
                  t('平均执行耗时'),
                  t(result.reuse?.reused_units ? '原始执行费用' : '估算费用'),
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
                  t('结果来源'),
                  t('原始执行费用'),
                  t('本次新增费用'),
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
                  <td>
                    {row.status === 'not_evaluable'
                      ? t('不可评估（缺少测试用例）')
                      : resultStatusLabel(row.status)}
                    {(failureDiagnosticLabel(row) ?? row.error_message) && (
                      <div>
                        {failureDiagnosticLabel(row) ?? row.error_message}
                      </div>
                    )}
                  </td>
                  <td>{metricLabel(row.iterations)}</td>
                  <td>{metricLabel(row.tokens)}</td>
                  <td>{metricLabel(row.execution_time, t('秒'))}</td>
                  <td>
                    {row.reused ? (
                      <>
                        {t('复用')}{' '}
                        {row.reuse_source && (
                          <Link
                            to={`/results/${encodeURIComponent(row.reuse_source.evaluation_id)}`}
                          >
                            {row.reuse_source.run_id}
                          </Link>
                        )}
                      </>
                    ) : (
                      t('新跑')
                    )}
                  </td>
                  <td>{metricLabel(row.original_cost_usd ?? null, 'USD')}</td>
                  <td>{metricLabel(row.new_cost_usd ?? null, 'USD')}</td>
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
