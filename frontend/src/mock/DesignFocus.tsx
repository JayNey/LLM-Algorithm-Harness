import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { Button } from 'antd'
import { runs, metrics, type MockRun } from './data.ts'
import type { AppearanceVariant } from '../store/ui.ts'
export function DesignFocus({
  design,
  go,
  inspect,
}: {
  design: AppearanceVariant
  go: (path: string) => void
  inspect: (run: MockRun) => void
}) {
  useTranslation()

  const running = runs[0],
    completed = runs.filter((r) => r.state === 'completed')
  const progress = Math.round((running.done / running.total) * 100)
  if (design === 'orbit')
    return (
      <section className="design-focus orbit-focus" aria-label={t('运行焦点')}>
        <div className="orbit-copy">
          <div className="focus-topline">
            <span className="live-indicator" />
            {t('运行焦点')}
            <span className="focus-id">{running.id} / Mock</span>
          </div>
          <h2>{running.name}</h2>
          <p>
            {running.model} · {running.dataset} · {running.strategy}
          </p>
          <div className="execution-stages" aria-label={t('执行阶段')}>
            <span className="stage-done">{t('✓ 初始化')}</span>
            <i />
            <strong>{t('执行题目')}</strong>
            <i />
            <span>{t('汇总结果')}</span>
          </div>
          <Button onClick={() => inspect(running)}>
            {t('检查当前运行 ')}
            <span aria-hidden="true">↗</span>
          </Button>
        </div>
        <div className="orbit-visual">
          <svg
            width="150"
            height="150"
            viewBox="0 0 150 150"
            role="img"
            aria-label={t('执行进度 ') + progress + '%'}
          >
            <circle
              cx="75"
              cy="75"
              r="62"
              fill="none"
              stroke="var(--line)"
              strokeWidth="1"
            />
            <circle
              cx="75"
              cy="75"
              r="49"
              fill="none"
              stroke="var(--line)"
              strokeWidth="8"
            />
            <circle
              cx="75"
              cy="75"
              r="49"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="8"
              strokeDasharray={`${(progress / 100) * 308} 308`}
              transform="rotate(-90 75 75)"
            />
            <text
              x="75"
              y="76"
              fill="var(--text)"
              textAnchor="middle"
              fontSize="29"
              fontWeight="550"
            >
              {progress}%
            </text>
            <text
              x="75"
              y="98"
              fill="var(--muted)"
              textAnchor="middle"
              fontSize="12"
            >
              {t('执行进度')}
            </text>
          </svg>
          <div>
            <strong>
              {running.done}
              <small>
                {' '}
                / {running.total} {t(' 题')}
              </small>
            </strong>
            <span>
              {t('调用费用 $')}
              {running.cost.toFixed(2)}
            </span>
          </div>
        </div>
      </section>
    )
  if (design === 'precision')
    return (
      <section
        className="design-focus precision-focus"
        aria-label={t('模型基线比较')}
      >
        <div className="precision-intro">
          <span>HumanEval / Direct</span>
          <h2>
            {t('同一基准，')}
            <br />
            {t('比较两种模型。')}
          </h2>
          <p>
            {metrics.total} {t(' 次执行 · 已完成任务')}
          </p>
          <Button onClick={() => go('/results')}>
            {t('查看结果 ')}
            <span aria-hidden="true">↗</span>
          </Button>
        </div>
        <div className="duel-models">
          {completed.map((r, i) => (
            <div className="duel-model" key={r.id}>
              <div className="model-label">
                <span className={'model-symbol ' + (i ? 'secondary' : '')} />
                {i ? 'DeepSeek-Coder-V2' : 'Qwen2.5-Coder'}
              </div>
              <strong>
                {((r.passed / r.total) * 100).toFixed(1)}
                <small>%</small>
              </strong>
              <span className="metric-caption">Pass@1</span>
              <div className="duel-track">
                <span style={{ width: (r.passed / r.total) * 100 + '%' }} />
              </div>
              <p>
                {r.passed} / {r.total} {t(' 通过 ')}
                <span>· ${r.cost.toFixed(2)}</span>
              </p>
            </div>
          ))}
        </div>
        <div className="precision-delta">
          <strong>
            4.2<small>pp</small>
          </strong>
          <p>
            {t('Qwen 基线领先')}
            <br />
            {t('按展示精度计算')}
          </p>
        </div>
      </section>
    )
  return (
    <section
      className="design-focus studio-focus"
      aria-label={t('实验工作笔记')}
    >
      <div className="journal-date">
        <strong>20</strong>
        <span>{t('10 月 · 2026')}</span>
        <small>{t('Mock 评估快照')}</small>
      </div>
      <div className="journal-copy">
        <span>{t('HumanEval 策略实验')}</span>
        <h2>{t('从基线到更好的解。')}</h2>
        <p>{t('用同一把尺子，记录模型、策略与每次尝试。')}</p>
        <Button onClick={() => go('/experiments')}>
          {t('打开实验笔记 ')}
          <span aria-hidden="true">↗</span>
        </Button>
      </div>
      <div className="method-list">
        <div>
          <span>Direct</span>
          <strong>{t('2 个已完成')}</strong>
        </div>
        <div>
          <span>Reflexion</span>
          <strong className="method-active">{t('1 个运行中')}</strong>
        </div>
        <div>
          <span>Self-refine</span>
          <strong>{t('1 个待检查')}</strong>
        </div>
      </div>
    </section>
  )
}
