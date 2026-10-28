import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { Button, Empty, Progress, Tooltip } from 'antd'
import { Icon } from '@/layouts/components/Icon.tsx'
import type { MockRun } from './data.ts'
const names = {
  get running() {
    return t('运行中')
  },
  get completed() {
    return t('已完成')
  },
  get failed() {
    return t('失败')
  },
}
export function Status({ state }: { state: MockRun['state'] }) {
  useTranslation()

  return (
    <span className={`status ${state}`}>
      <span className="status-mark" aria-hidden="true">
        {state === 'completed' ? '✓' : state === 'failed' ? '!' : '◌'}
      </span>
      {names[state]}
    </span>
  )
}
export function RunList({
  rows,
  inspect,
  clear,
}: {
  rows: MockRun[]
  inspect: (run: MockRun) => void
  clear: () => void
}) {
  useTranslation()

  return (
    <div className="run-list">
      {rows.length === 0 ? (
        <Empty description={t('没有匹配的评估任务')}>
          <Button onClick={clear}>{t('清除筛选')}</Button>
        </Empty>
      ) : (
        <div role="table" aria-label={t('Mock 评估任务')}>
          <div className="table-head" role="row">
            {[
              t('评估任务 / 模型'),
              t('数据集'),
              t('状态'),
              'Pass@1',
              t('费用'),
              t('详情'),
            ].map((label, i) => (
              <span
                role="columnheader"
                key={label}
                className={i === 3 || i === 4 ? 'num' : ''}
              >
                {label}
              </span>
            ))}
          </div>
          {rows.map((run) => (
            <div className="run-row" role="row" key={run.id}>
              <div className="run-identity" role="cell">
                <button className="row-name" onClick={() => inspect(run)}>
                  {run.name}
                </button>
                <span className="muted model" title={run.model}>
                  {run.model} <span className="run-id">/ {run.id}</span>
                </span>
              </div>
              <div className="dataset" role="cell">
                <span className="mobile-label">{t('数据集 ')}</span>
                {run.dataset}
                <small>{run.strategy}</small>
              </div>
              <div className="run-status" role="cell">
                <Status state={run.state} />
                {run.state === 'running' && (
                  <Progress
                    percent={Math.round((run.done / run.total) * 100)}
                    showInfo={false}
                    size="small"
                    aria-label={t('评估进度 {{value1}} / {{value2}}', {
                      value1: run.done,
                      value2: run.total,
                    })}
                  />
                )}
              </div>
              <div className="num score" role="cell">
                <span className="mobile-label">Pass@1 </span>
                {run.state === 'completed' ? (
                  `${((run.passed / run.total) * 100).toFixed(1)}%`
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
              <div className="num cost" role="cell">
                <span className="mobile-label">{t('费用 ')}</span>$
                {run.cost.toFixed(2)}
              </div>
              <div role="cell" className="run-action">
                <Tooltip title={t('查看任务详情')}>
                  <Button
                    type="text"
                    aria-label={t('查看 {{value1}}', { value1: run.name })}
                    icon={<Icon name="arrow" />}
                    onClick={() => inspect(run)}
                  />
                </Tooltip>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
