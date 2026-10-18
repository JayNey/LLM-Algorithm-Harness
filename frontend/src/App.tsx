import { Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { RequireSession } from '@/components/Auth/RequireSession.tsx'
import { AppLayout } from '@/layouts/AppLayout.tsx'
import { AuthLayout } from '@/layouts/AuthLayout.tsx'
import { appPages, authPages, settingsPages } from '@/routes.tsx'
import { useAuthStore } from '@/store/auth.ts'

useAuthStore.getState().hydrate()

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AuthLayout />}>
          {authPages.map((page) => (
            <Route
              key={page.path}
              path={page.path}
              element={
                <Suspense fallback={<p>加载中</p>}>
                  <page.Component />
                </Suspense>
              }
            />
          ))}
        </Route>
        <Route element={<RequireSession />}>
          <Route element={<AppLayout />}>
            {appPages.map((page) => (
              <Route
                key={page.path}
                path={page.path}
                element={
                  <Suspense fallback={<p>加载中</p>}>
                    <page.Component />
                  </Suspense>
                }
              />
            ))}
            {settingsPages.map((page) => (
              <Route
                key={page.path}
                path={page.path}
                element={
                  <Suspense fallback={<p>加载中</p>}>
                    <page.Component />
                  </Suspense>
                }
              />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
