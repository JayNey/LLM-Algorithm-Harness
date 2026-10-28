import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { Button, Checkbox, Input } from 'antd'
import type { SuiteDraft, SuiteDraftErrors } from './types.ts'

export function SuiteForm({
  draft,
  errors,
  onChange,
  onSubmit,
  onCancel,
  busy,
  submitLabel,
  disableName = false,
}: {
  draft: SuiteDraft
  errors: SuiteDraftErrors
  onChange: (patch: Partial<SuiteDraft>) => void
  onSubmit: () => void
  onCancel: () => void
  busy: boolean
  submitLabel: string
  /** 编辑态名称不可改：后端 PATCH 无 name 字段 */
  disableName?: boolean
}) {
  useTranslation()

  return (
    <div className="panel evaluation-panel">
      <label>
        {t('套件名称')}
        <Input
          aria-label={t('套件名称')}
          value={draft.name}
          maxLength={200}
          disabled={disableName}
          onChange={(event) => onChange({ name: event.target.value })}
        />
        {errors.name && <small role="alert">{t(errors.name)}</small>}
      </label>
      <label>
        {t('版本')}
        <Input
          aria-label={t('套件版本')}
          value={draft.version}
          maxLength={32}
          onChange={(event) => onChange({ version: event.target.value })}
        />
        {errors.version && <small role="alert">{t(errors.version)}</small>}
      </label>
      <label>
        {t('描述（可选）')}
        <Input
          aria-label={t('套件描述')}
          value={draft.description}
          onChange={(event) => onChange({ description: event.target.value })}
        />
      </label>
      <label>
        {t('题目 ID（每行一个）')}
        <Input.TextArea
          aria-label={t('套件题目列表')}
          rows={5}
          value={draft.problems_text}
          onChange={(event) => onChange({ problems_text: event.target.value })}
        />
        {errors.problems_text && (
          <small role="alert">{t(errors.problems_text)}</small>
        )}
      </label>
      <Checkbox
        aria-label={t('冻结套件')}
        checked={draft.frozen}
        onChange={(event) => onChange({ frozen: event.target.checked })}
      >
        {t('冻结（固定题集，用于长期学习曲线追踪）')}
      </Checkbox>
      <div className="evaluation-section-heading">
        <Button
          type="primary"
          aria-label={submitLabel}
          disabled={busy}
          onClick={onSubmit}
        >
          {submitLabel}
        </Button>
        <Button onClick={onCancel} disabled={busy}>
          {t('取消')}
        </Button>
      </div>
    </div>
  )
}
