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
  const running = runs[0],
    completed = runs.filter((r) => r.state === 'completed')
  const progress = Math.round((running.done / running.total) * 100)
  if (design === 'orbit')
    return (
      <section className="design-focus orbit-focus" aria-label="运行焦点">
        <div className="orbit-copy">
          <div className="focus-topline">
            <span className="live-indicator" />
            运行焦点<span className="focus-id">{running.id} / Mock</span>
          </div>
          <h2>{running.name}</h2>
          <p>
            {running.model} · {running.dataset} · {running.strategy}
          </p>
          <div className="execution-stages" aria-label="执行阶段">
            <span className="stage-done">✓ 初始化</span>
            <i />
            <strong>执行题目</strong>
            <i />
            <span>汇总结果</span>
          </div>
          <Button onClick={() => inspect(running)}>
            检查当前运行 <span aria-hidden="true">↗</span>
          </Button>
        </div>
        <div className="orbit-visual">
          <svg
            width="150"
            height="150"
            viewBox="0 0 150 150"
            role="img"
            aria-label={'执行进度 ' + progress + '%'}
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
              执行进度
            </text>
          </svg>
          <div>
            <strong>
              {running.done}
              <small> / {running.total} 题</small>
            </strong>
            <span>调用费用 ${running.cost.toFixed(2)}</span>
          </div>
        </div>
      </section>
    )
  if (design === 'precision')
    return (
      <section
        className="design-focus precision-focus"
        aria-label="模型基线比较"
      >
        <div className="precision-intro">
          <span>HumanEval / Direct</span>
          <h2>
            同一基准，
            <br />
            比较两种模型。
          </h2>
          <p>{metrics.total} 次执行 · 已完成任务</p>
          <Button onClick={() => go('/results')}>
            查看结果 <span aria-hidden="true">↗</span>
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
                {r.passed} / {r.total} 通过 <span>· ${r.cost.toFixed(2)}</span>
              </p>
            </div>
          ))}
        </div>
        <div className="precision-delta">
          <strong>
            4.2<small>pp</small>
          </strong>
          <p>
            Qwen 基线领先
            <br />
            按展示精度计算
          </p>
        </div>
      </section>
    )
  return (
    <section className="design-focus studio-focus" aria-label="实验工作笔记">
      <div className="journal-date">
        <strong>20</strong>
        <span>10 月 · 2026</span>
        <small>Mock 评估快照</small>
      </div>
      <div className="journal-copy">
        <span>HumanEval 策略实验</span>
        <h2>从基线到更好的解。</h2>
        <p>用同一把尺子，记录模型、策略与每次尝试。</p>
        <Button onClick={() => go('/experiments')}>
          打开实验笔记 <span aria-hidden="true">↗</span>
        </Button>
      </div>
      <div className="method-list">
        <div>
          <span>Direct</span>
          <strong>2 个已完成</strong>
        </div>
        <div>
          <span>Reflexion</span>
          <strong className="method-active">1 个运行中</strong>
        </div>
        <div>
          <span>Self-refine</span>
          <strong>1 个待检查</strong>
        </div>
      </div>
    </section>
  )
}
