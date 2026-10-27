import {
  App as AntApp,
  Button,
  ConfigProvider,
  Drawer,
  Dropdown,
  Tooltip,
} from 'antd'
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { readViteEnv } from '@/config/env.ts'
import { useAuthStore } from '@/store/auth.ts'
import { appearanceVariants, useUiStore } from '@/store/ui.ts'
import { ErrorBoundary } from '@/components/common/Feedback.tsx'
import { EvaluationSessionProvider } from '@/evaluations/session.tsx'
import { ExperimentSessionProvider } from '@/experiments/session.tsx'
import { BenchmarkSessionProvider } from '@/benchmarks/session.tsx'
import { ABTestSessionProvider } from '@/abtests/session.tsx'
import { ProblemSessionProvider } from '@/problems/session.tsx'
import { BudgetSessionProvider } from '@/budgets/session.tsx'
import { PricingSessionProvider } from '@/pricing/session.tsx'
import { SystemLogSessionProvider } from '@/systemlogs/session.tsx'
import { MockActions } from '@/mock/MockActions.tsx'
import { appearanceTheme } from './appearance.ts'
import { Icon } from './components/Icon.tsx'
import {
  AppearanceControls,
  Breadcrumb,
  MobileNav,
  Navigation,
} from './components/Navigation.tsx'
import { NotificationCenter } from './components/NotificationCenter.tsx'
const appName = readViteEnv().appName
const wordmark = appName === 'LLM Algorithm Harness' ? 'Harness' : appName
function subscribeMotion(change: () => void) {
  const media = window.matchMedia('(prefers-reduced-motion: reduce)')
  media.addEventListener('change', change)
  return () => media.removeEventListener('change', change)
}
export function AppLayout() {
  const reducedMotion = useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    () => false,
  )
  const { appearanceVariant, colorScheme } = useUiStore()
  return (
    <ConfigProvider
      theme={appearanceTheme(appearanceVariant, colorScheme, reducedMotion)}
    >
      <AntApp>
        <Shell />
      </AntApp>
    </ConfigProvider>
  )
}
function Shell() {
  const navigate = useNavigate()
  const location = useLocation()
  const session = useAuthStore((state) => state.session)
  const logout = useAuthStore((state) => state.logout)
  const ui = useUiStore()
  const username = session?.username || '已登录'
  const [openedAt, setOpenedAt] = useState<string | null>(null)
  const [modal, setModal] = useState<'import' | null>(null)
  const main = useRef<HTMLElement>(null)
  const menu = useRef<HTMLButtonElement>(null)
  const drawerOpen = openedAt === location.key
  // Rapid Escape can close the drawer before its animation callback runs.
  const drawerWasOpen = useRef(false)
  useEffect(() => {
    if (drawerWasOpen.current && !drawerOpen) menu.current?.focus()
    drawerWasOpen.current = drawerOpen
  }, [drawerOpen])
  useEffect(() => {
    main.current?.focus()
  }, [location.pathname])
  async function signOut() {
    try {
      await logout()
    } catch {
      /* Existing logout always clears the local session. */
    } finally {
      navigate('/login', { replace: true })
    }
  }
  function onCreate() {
    setOpenedAt(null)
    navigate('/evaluations/new')
  }
  function onImport() {
    setOpenedAt(null)
    setModal('import')
  }
  const actions = { onCreate, onImport }
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          e.preventDefault()
          main.current?.focus()
        }}
      >
        跳至主内容
      </a>
      <div className={`app-shell ${ui.sidebarCollapsed ? 'collapsed' : ''}`}>
        <aside className="sidebar">
          <Navigation {...actions} collapsed={ui.sidebarCollapsed} />
          <Tooltip title={ui.sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}>
            <button
              className="collapse-button"
              aria-label={ui.sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
              aria-expanded={!ui.sidebarCollapsed}
              onClick={ui.toggleSidebar}
            >
              <Icon name="collapse" />
              <span>折叠侧边栏</span>
            </button>
          </Tooltip>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div className="topbar-left">
              <Button
                ref={menu}
                className="mobile-menu"
                type="text"
                aria-label="打开导航菜单"
                aria-expanded={drawerOpen}
                onClick={() => setOpenedAt(location.key)}
                icon={<Icon name="menu" />}
              />
              <span className="top-product">
                <img
                  src="/brand/harness-frontier.svg"
                  alt=""
                  width={24}
                  height={24}
                />
                <span className="product-name" title={appName}>
                  {wordmark}
                </span>
              </span>
              <span className="workspace-label">
                {appearanceVariants[ui.appearanceVariant].en} / 个人工作空间
              </span>
            </div>
            <div className="top-actions">
              <Dropdown
                trigger={['click']}
                menu={{
                  items: [
                    { key: 'create', label: '创建评估' },
                    { key: 'import', label: '导入题目' },
                  ],
                  onClick: ({ key }) =>
                    key === 'create' ? onCreate() : onImport(),
                }}
              >
                <Button className="quick-actions" type="text">
                  快速操作 <Icon name="chevron" size={14} />
                </Button>
              </Dropdown>
              <Tooltip
                title={ui.colorScheme === 'dark' ? '切换至浅色' : '切换至深色'}
              >
                <Button
                  type="text"
                  aria-label={
                    ui.colorScheme === 'dark'
                      ? '切换至浅色主题'
                      : '切换至深色主题'
                  }
                  icon={
                    <Icon name={ui.colorScheme === 'dark' ? 'sun' : 'moon'} />
                  }
                  onClick={ui.toggleColorScheme}
                />
              </Tooltip>
              <NotificationCenter
                key={session?.marker ?? 'anonymous'}
                owner={session?.marker ?? 'anonymous'}
              />
              <span className="username-label" title={username}>
                {username}
              </span>
              <Dropdown
                trigger={['click']}
                menu={{
                  items: [
                    { key: '/settings/profile', label: '个人资料' },
                    { key: '/settings/api-keys', label: 'API 密钥管理' },
                    { key: '/help', label: '帮助文档' },
                    { type: 'divider' },
                    { key: 'logout', label: '登出' },
                  ],
                  onClick: ({ key }) =>
                    key === 'logout' ? void signOut() : navigate(key),
                }}
              >
                <button className="avatar" aria-label={`用户菜单：${username}`}>
                  {username.slice(0, 1)}
                </button>
              </Dropdown>
            </div>
          </header>
          <main className="sheet" id="main" ref={main} tabIndex={-1}>
            <AppearanceControls />
            <Breadcrumb />
            <div className="route-content">
              <EvaluationSessionProvider>
                <ExperimentSessionProvider>
                  <BenchmarkSessionProvider>
                    <ABTestSessionProvider>
                      <ProblemSessionProvider>
                        <BudgetSessionProvider>
                          <PricingSessionProvider>
                            <SystemLogSessionProvider>
                              <ErrorBoundary key={location.pathname}>
                                <Outlet context={actions} />
                              </ErrorBoundary>
                            </SystemLogSessionProvider>
                          </PricingSessionProvider>
                        </BudgetSessionProvider>
                      </ProblemSessionProvider>
                    </ABTestSessionProvider>
                  </BenchmarkSessionProvider>
                </ExperimentSessionProvider>
              </EvaluationSessionProvider>
            </div>
            <footer className="workspace-footer">
              <span>{appName}</span>
              <span>{appearanceVariants[ui.appearanceVariant].name}</span>
            </footer>
          </main>
        </div>
      </div>
      <MobileNav />
      <Drawer
        title="工作台导航"
        placement="left"
        open={drawerOpen}
        focusable={{ focusTriggerAfterClose: false }}
        onClose={() => setOpenedAt(null)}
        afterOpenChange={(open) => {
          if (!open) menu.current?.focus()
        }}
        size={280}
        className="navigation-drawer"
      >
        <Navigation {...actions} onNavigate={() => setOpenedAt(null)} />
      </Drawer>
      <MockActions
        key={session?.marker ?? 'anonymous'}
        mode={modal}
        onClose={() => setModal(null)}
      />
    </>
  )
}
