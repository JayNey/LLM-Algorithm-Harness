import { Button, ConfigProvider, theme } from 'antd'
import { Navigate, NavLink, Outlet } from 'react-router-dom'
import { readViteEnv } from '@/config/env.ts'
import { authPages } from '@/routes.tsx'
import { useAuthStore } from '@/store/auth.ts'
import { useUiStore } from '@/store/ui.ts'

const appName = readViteEnv().appName

export function AuthLayout() {
  const session = useAuthStore((state) => state.session)
  const colorScheme = useUiStore((state) => state.colorScheme)
  const toggleColorScheme = useUiStore((state) => state.toggleColorScheme)

  if (session !== null) {
    return <Navigate to="/" replace />
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
            <Button onClick={toggleColorScheme}>
              {colorScheme === 'dark' ? '浅色' : '深色'}
            </Button>
          </div>
          <nav className="mt-3 flex flex-row flex-wrap gap-2">
            {authPages.map((page) => (
              <NavLink
                key={page.path}
                to={page.path}
                className={({ isActive }) =>
                  isActive ? 'font-semibold underline' : undefined
                }
              >
                {page.label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main className="p-4">
          <Outlet />
        </main>
      </div>
    </ConfigProvider>
  )
}
