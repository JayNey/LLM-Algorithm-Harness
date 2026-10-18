import { Button, ConfigProvider, theme } from 'antd'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { readViteEnv } from '@/config/env.ts'
import { appPages } from '@/routes.tsx'
import { useAuthStore } from '@/store/auth.ts'
import { useUiStore } from '@/store/ui.ts'

const appName = readViteEnv().appName

export function AppLayout() {
  const navigate = useNavigate()
  const session = useAuthStore((state) => state.session)
  const logout = useAuthStore((state) => state.logout)
  const colorScheme = useUiStore((state) => state.colorScheme)
  const toggleColorScheme = useUiStore((state) => state.toggleColorScheme)
  const [menuOpen, setMenuOpen] = useState(false)

  async function signOut() {
    try {
      await logout()
    } catch {
      // logout 清除本地会话后会重新抛出，失败时仍离开业务页。
    } finally {
      navigate('/login', { replace: true })
    }
  }

  return (
    <ConfigProvider
      theme={{
        algorithm:
          colorScheme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
      }}
    >
      <div className="min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
        <header className="border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
          <div className="flex items-center justify-between gap-3">
            <strong>{appName}</strong>
            <div className="flex items-center gap-2">
              <span>{session?.username || '已登录'}</span>
              <Button
                className="md:hidden"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((open) => !open)}
              >
                菜单
              </Button>
              <Button onClick={toggleColorScheme}>
                {colorScheme === 'dark' ? '浅色' : '深色'}
              </Button>
            </div>
          </div>
          <nav
            className={`${menuOpen ? 'flex' : 'hidden'} mt-3 flex-col gap-2 md:mt-3 md:flex md:flex-row md:flex-wrap`}
          >
            {appPages.map((page) => (
              <NavLink
                key={page.path}
                to={page.path}
                end={page.path === '/'}
                className={({ isActive }) =>
                  isActive ? 'font-semibold underline' : undefined
                }
                onClick={() => setMenuOpen(false)}
              >
                {page.label}
              </NavLink>
            ))}
            <Button onClick={() => void signOut()}>登出</Button>
          </nav>
        </header>
        <main className="p-4">
          <Outlet />
        </main>
      </div>
    </ConfigProvider>
  )
}
