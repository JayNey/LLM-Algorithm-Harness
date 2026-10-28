import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { LanguageSelect } from '@/i18n/LocaleProvider.tsx'
import { Button, Tooltip } from 'antd'
import { Link, NavLink, matchPath, useLocation } from 'react-router-dom'
import { appPages, detailPages, settingsPages } from '@/routes.tsx'
import { useRole } from '@/auth/roleContext.ts'
import { canAccess } from '@/auth/roles.ts'
import { readViteEnv } from '@/config/env.ts'
import { useUiStore } from '@/store/ui.ts'
import { Icon } from './Icon.tsx'
const appName = readViteEnv().appName
const wordmark = appName === 'LLM Algorithm Harness' ? 'Harness' : appName
export function Navigation({
  onCreate,
  onImport,
  onNavigate,
  collapsed = false,
}: {
  onCreate: () => void
  onImport: () => void
  onNavigate?: () => void
  collapsed?: boolean
}) {
  useTranslation()

  const { state } = useRole()
  const pages = [...appPages, ...settingsPages.filter((p) => p.group)].filter(
    (p) => canAccess(state.role, p.allowedRoles),
  )
  return (
    <>
      <Link
        to="/"
        onClick={onNavigate}
        className="brand"
        aria-label={t('{{value1}} 仪表盘', { value1: appName })}
      >
        <img
          className="brand-mark"
          src="/brand/harness-frontier.svg"
          alt=""
          width={34}
          height={34}
        />
        <div title={appName}>
          {wordmark}
          <span>LLM Algorithm</span>
        </div>
      </Link>
      <div className="scope">
        <span className="scope-dot" />
        <span>{t('算法评估工作台')}</span>
      </div>
      <nav aria-label={t('主导航')}>
        {['评估工作台', '分析与对比', '系统'].map((group) => (
          <div className="nav-group" key={group}>
            <div className="group-label">{t(group)}</div>
            {pages
              .filter((p) => p.group === group)
              .map((page) => (
                <Tooltip
                  key={page.path}
                  title={collapsed ? page.label : undefined}
                  placement="right"
                >
                  <NavLink
                    to={page.path}
                    end={page.path === '/'}
                    aria-label={page.label}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `nav-link ${isActive ? 'active' : ''}`
                    }
                  >
                    <Icon name={page.icon ?? 'grid'} />
                    <span>{page.label}</span>
                  </NavLink>
                </Tooltip>
              ))}
          </div>
        ))}
      </nav>
      <div className="side-bottom">
        <Button onClick={onCreate} icon={<Icon name="plus" />} block>
          {t('创建评估')}
        </Button>
        <button className="import-button" onClick={onImport}>
          <Icon name="upload" />
          <span>{t('导入题目')}</span>
        </button>
      </div>
    </>
  )
}
export function MobileNav() {
  useTranslation()

  return (
    <nav className="bottom-nav" aria-label={t('常用页面')}>
      {appPages
        .filter((p) =>
          ['/', '/problems', '/evaluations', '/results'].includes(p.path),
        )
        .map((page) => (
          <NavLink
            key={page.path}
            to={page.path}
            end={page.path === '/'}
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            <Icon name={page.icon ?? 'grid'} />
            <span>
              {page.label
                .replace(t('评估任务'), t('评估'))
                .replace(t('评估结果'), t('结果'))}
            </span>
          </NavLink>
        ))}
    </nav>
  )
}
export function Breadcrumb() {
  useTranslation()

  const { pathname } = useLocation()
  const page = [...appPages, ...settingsPages, ...detailPages].find((p) =>
    matchPath({ path: p.path, end: true }, pathname),
  )
  return (
    <nav className="breadcrumbs" aria-label={t('面包屑')}>
      <Link to="/">{t('工作台')}</Link>
      <span aria-hidden="true">/</span>
      {pathname.startsWith('/settings/') && (
        <>
          <Link to="/settings">{t('设置')}</Link>
          <span aria-hidden="true">/</span>
        </>
      )}
      <span aria-current="page">{page?.label ?? t('页面未找到')}</span>
    </nav>
  )
}
export function AppearanceControls() {
  useTranslation()

  const ui = useUiStore()
  return (
    <div className="design-chooser">
      <LanguageSelect />
      <label htmlFor="design-select">
        <span>{t('当前风格')}</span>
        <select
          id="design-select"
          aria-label={t('选择页面风格')}
          value={ui.appearanceVariant}
          onChange={(e) =>
            ui.setAppearanceVariant(
              e.target.value as typeof ui.appearanceVariant,
            )
          }
        >
          <option value="orbit">{t('深空控制台')}</option>
          <option value="precision">{t('精密实验室')}</option>
          <option value="studio">{t('石墨工作室')}</option>
        </select>
      </label>
      <label htmlFor="theme-select">
        <span>{t('主题')}</span>
        <select
          id="theme-select"
          aria-label={t('主题偏好')}
          value={ui.themePreference}
          onChange={(e) =>
            ui.setThemePreference(e.target.value as typeof ui.themePreference)
          }
        >
          <option value="light">{t('浅色')}</option>
          <option value="dark">{t('深色')}</option>
          <option value="system">{t('跟随系统')}</option>
        </select>
      </label>
    </div>
  )
}
