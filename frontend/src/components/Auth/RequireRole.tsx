import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button, Result } from 'antd'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useRole } from '@/auth/roleContext.ts'
import { canAccess, type UserRole } from '@/auth/roles.ts'

export function RequireRole({
  allowedRoles,
  children,
}: {
  allowedRoles?: readonly UserRole[]
  children: ReactNode
}) {
  useTranslation()

  const { state, reload } = useRole()
  if (allowedRoles !== undefined && state.status === 'loading')
    return <p role="status">{t('正在确认访问权限…')}</p>
  if (allowedRoles !== undefined && state.status === 'error')
    return (
      <Result
        status="warning"
        title={t('无法确认访问权限')}
        subTitle={t('请检查网络连接后重试。')}
        extra={<Button onClick={reload}>{t('重试')}</Button>}
      />
    )
  if (!canAccess(state.role, allowedRoles))
    return (
      <Result
        status="403"
        title={t('无权访问此页面')}
        subTitle={t('此页面仅对管理员开放。')}
        extra={<Link to="/settings">{t('返回设置')}</Link>}
      />
    )
  return children
}
