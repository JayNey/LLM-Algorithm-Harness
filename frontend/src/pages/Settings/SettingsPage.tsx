import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Link } from 'react-router-dom'
import { settingsPages } from '@/routes.tsx'
import { useRole } from '@/auth/roleContext.ts'
import { canAccess } from '@/auth/roles.ts'

export default function SettingsPage() {
  useTranslation()

  const { state } = useRole()
  return (
    <section>
      <h1>{t('设置')}</h1>
      {settingsPages
        .filter((page) => canAccess(state.role, page.allowedRoles))
        .map((page) => (
          <p key={page.path}>
            <Link to={page.path}>{page.label}</Link>
          </p>
        ))}
    </section>
  )
}
