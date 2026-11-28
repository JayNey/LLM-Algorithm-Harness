import { Input, Select } from 'antd'
import { t } from '../i18n/core.ts'
import {
  budgetDraft,
  filterSummary,
  problemFilters,
  strategyControls,
} from './advanced.ts'
import { budgetKindLabels } from './presentation.ts'
import type { DraftErrors, ExperimentDraft, StrategyConfig } from './types.ts'

export function StrategyAdvancedFields({
  strategy,
  index,
  update,
  disabled,
  errors,
}: {
  strategy: ExperimentDraft['strategies'][number]
  index: number
  update(patch: Partial<ExperimentDraft['strategies'][number]>): void
  disabled: boolean
  errors: DraftErrors
}) {
  const controls = strategyControls[strategy.name.trim()] ?? {}
  return (
    <details style={{ flexBasis: '100%', minWidth: 0 }}>
      <summary>
        {t('高级策略配置')} · {index + 1}
      </summary>
      <label>
        {t('最大生成 Token（可选）')}
        <Input
          aria-label={t('策略 {{index}} 最大生成 Token', { index: index + 1 })}
          value={strategy.max_tokens ?? ''}
          placeholder="100–8000"
          onChange={(event) => update({ max_tokens: event.target.value })}
          disabled={disabled}
          aria-invalid={!!errors[`strategies.${index}.max_tokens`]}
        />
        {errors[`strategies.${index}.max_tokens`] && (
          <small role="alert">
            {t(errors[`strategies.${index}.max_tokens`])}
          </small>
        )}
      </label>
      <label>
        {t('系统提示词（可选）')}
        <Input.TextArea
          aria-label={t('策略 {{index}} 系统提示词', { index: index + 1 })}
          value={strategy.system_prompt ?? ''}
          onChange={(event) => update({ system_prompt: event.target.value })}
          autoSize={{ minRows: 2, maxRows: 8 }}
          disabled={disabled}
        />
      </label>
      <label>
        {t('自定义策略参数（JSON，可选）')}
        <Input.TextArea
          aria-label={t('策略 {{index}} 自定义参数', { index: index + 1 })}
          value={strategy.custom_params ?? ''}
          placeholder={
            strategy.name === 'self_consistency'
              ? '{"num_candidates": 3}'
              : '{}'
          }
          onChange={(event) => update({ custom_params: event.target.value })}
          autoSize={{ minRows: 2, maxRows: 8 }}
          disabled={disabled}
          aria-invalid={!!errors[`strategies.${index}.custom_params`]}
        />
        {errors[`strategies.${index}.custom_params`] && (
          <small role="alert">
            {t(errors[`strategies.${index}.custom_params`])}
          </small>
        )}
      </label>
      <p>
        {t(
          '留空继承现有默认。仅支持下列策略参数，不支持路径、连接地址或沙箱配置。',
        )}
      </p>
      {Object.keys(controls).length ? (
        <ul>
          {Object.entries(controls).map(([key, rule]) => (
            <li key={key}>
              <code>{key}</code>:{' '}
              {rule.values?.join(' / ') ??
                `${rule.integer ? t('整数') : t('数值')} ≥ ${rule.min}${rule.max === undefined ? '' : ` ≤ ${rule.max}`}`}
            </li>
          ))}
        </ul>
      ) : (
        <p>{t('当前策略无可配置的自定义参数')}</p>
      )}
    </details>
  )
}

export function ProblemFilterFields({
  draft,
  update,
  disabled,
  errors,
  kind,
}: {
  draft: Pick<ExperimentDraft, 'problem_filters'>
  update(patch: Pick<ExperimentDraft, 'problem_filters'>): void
  disabled: boolean
  kind?: 'abtest'
  errors: DraftErrors
}) {
  const raw = draft.problem_filters ?? {}
  const change = (patch: Partial<typeof raw>) =>
    update({ problem_filters: { ...raw, ...patch } })
  return (
    <fieldset>
      <legend>{t('题目筛选（可选）')}</legend>
      <label>
        {t('难度')}
        <Select
          aria-label={kind === 'abtest' ? t('题目筛选难度') : t('实验筛选难度')}
          value={raw.difficulty || undefined}
          allowClear
          placeholder={t('全部难度')}
          options={['easy', 'medium', 'hard'].map((value) => ({
            value,
            label: value,
          }))}
          onChange={(value) => change({ difficulty: value ?? '' })}
          disabled={disabled}
        />
        {errors['problem_filters.difficulty'] && (
          <small role="alert">{t(errors['problem_filters.difficulty'])}</small>
        )}
      </label>
      <label>
        {t('标签（任一匹配）')}
        <Input.TextArea
          aria-label={kind === 'abtest' ? t('题目筛选标签') : t('实验筛选标签')}
          value={raw.tags ?? ''}
          placeholder={t('以逗号或换行分隔')}
          onChange={(event) => change({ tags: event.target.value })}
          disabled={disabled}
        />
      </label>
      <label>
        {t('题目 ID 白名单')}
        <Input.TextArea
          aria-label={
            kind === 'abtest' ? t('题目筛选题目 ID') : t('实验筛选题目 ID')
          }
          value={raw.problem_ids ?? ''}
          placeholder={t('以逗号或换行分隔')}
          onChange={(event) => change({ problem_ids: event.target.value })}
          disabled={disabled}
        />
      </label>
      <label>
        {t('题目数量上限')}
        <Input
          aria-label={
            kind === 'abtest' ? t('题目筛选数量上限') : t('实验筛选数量上限')
          }
          value={raw.limit ?? ''}
          onChange={(event) => change({ limit: event.target.value })}
          disabled={disabled}
          aria-invalid={!!errors['problem_filters.limit']}
        />
        {errors['problem_filters.limit'] && (
          <small role="alert">{t(errors['problem_filters.limit'])}</small>
        )}
      </label>
      <p>
        {t(
          '标签任一匹配；各条件取交集，最后按数据集顺序截取数量。实际匹配题数在执行后确认。',
        )}
      </p>
      <p role="status">{filterSummary(problemFilters(draft))}</p>
    </fieldset>
  )
}

export function BudgetFields({
  draft,
  update,
  disabled,
  errors,
}: {
  draft: ExperimentDraft
  update(patch: Partial<ExperimentDraft>): void
  disabled: boolean
  errors: DraftErrors
}) {
  const values = budgetDraft(draft)
  return (
    <fieldset>
      <legend>{t('每题预算（可组合，可选）')}</legend>
      {(['max_calls', 'max_tokens', 'max_seconds'] as const).map((kind) => (
        <label key={kind}>
          {budgetKindLabels[kind]}
          <Input
            aria-label={t('实验预算 {{kind}}', { kind })}
            value={values[kind] ?? ''}
            onChange={(event) =>
              update({ budget: { ...values, [kind]: event.target.value } })
            }
            disabled={disabled}
            aria-invalid={!!errors[`budget.${kind}`]}
          />
          {errors[`budget.${kind}`] && (
            <small role="alert">{t(errors[`budget.${kind}`])}</small>
          )}
        </label>
      ))}
      <p>
        {t(
          '留空不限制。每题重置，任一上限触发后停止后续调用；Token 按已知用量结算，时间为每题墙钟时间。',
        )}
      </p>
    </fieldset>
  )
}

export function StrategySummary({
  strategies,
}: {
  strategies: StrategyConfig[]
}) {
  return (
    <ul>
      {strategies.map((strategy, index) => {
        const settings = {
          ...(strategy.max_iterations !== undefined
            ? { max_iterations: strategy.max_iterations }
            : {}),
          ...(strategy.temperature !== undefined
            ? { temperature: strategy.temperature }
            : {}),
          ...(strategy.max_tokens !== undefined
            ? { max_tokens: strategy.max_tokens }
            : {}),
          ...(strategy.system_prompt != null
            ? { system_prompt: strategy.system_prompt }
            : {}),
          ...(strategy.custom_params &&
          Object.keys(strategy.custom_params).length
            ? { custom_params: strategy.custom_params }
            : {}),
        }
        return (
          <li key={index}>
            <strong>{strategy.name}</strong>
            {Object.keys(settings).length ? (
              <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                {JSON.stringify(settings, null, 2)}
              </pre>
            ) : (
              <p>{t('使用现有默认配置')}</p>
            )}
          </li>
        )
      })}
    </ul>
  )
}
