import { Button, Tooltip } from 'antd'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { appPages, settingsPages } from '@/routes.tsx'
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
        aria-label={`${appName} 仪表盘`}
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
        <span>算法评估工作台</span>
      </div>
      <nav aria-label="主导航">
        {['评估工作台', '分析与对比', '系统'].map((group) => (
          <div className="nav-group" key={group}>
            <div className="group-label">{group}</div>
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
          创建评估
        </Button>
        <button className="import-button" onClick={onImport}>
          <Icon name="upload" />
          <span>导入题目</span>
        </button>
        <div className="mock-note">
          <span className="scope-dot" />
          业务与通知 · Mock
        </div>
      </div>
    </>
  )
}
export function MobileNav() {
  return (
    <nav className="bottom-nav" aria-label="常用页面">
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
                .replace('评估任务', '评估')
                .replace('评估结果', '结果')}
            </span>
          </NavLink>
        ))}
    </nav>
  )
}
export function Breadcrumb() {
  const { pathname } = useLocation()
  const page = [...appPages, ...settingsPages].find((p) => p.path === pathname)
  return (
    <nav className="breadcrumbs" aria-label="面包屑">
      <Link to="/">工作台</Link>
      <span aria-hidden="true">/</span>
      {pathname.startsWith('/settings/') && (
        <>
          <Link to="/settings">设置</Link>
          <span aria-hidden="true">/</span>
        </>
      )}
      <span aria-current="page">{page?.label ?? '页面未找到'}</span>
    </nav>
  )
}
export function AppearanceControls() {
  const ui = useUiStore()
  return (
    <div className="design-chooser">
      <label htmlFor="design-select">当前风格</label>
      <select
        id="design-select"
        aria-label="选择页面风格"
        value={ui.appearanceVariant}
        onChange={(e) =>
          ui.setAppearanceVariant(e.target.value as typeof ui.appearanceVariant)
        }
      >
        <option value="orbit">深空控制台</option>
        <option value="precision">精密实验室</option>
        <option value="studio">石墨工作室</option>
      </select>
      <label htmlFor="theme-select">主题</label>
      <select
        id="theme-select"
        aria-label="主题偏好"
        value={ui.themePreference}
        onChange={(e) =>
          ui.setThemePreference(e.target.value as typeof ui.themePreference)
        }
      >
        <option value="light">浅色</option>
        <option value="dark">深色</option>
        <option value="system">跟随系统</option>
      </select>
      <small className="mobile-mock">业务与通知 · Mock</small>
    </div>
  )
}
