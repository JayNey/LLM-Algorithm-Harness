import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { sanitizeReturnPath } from '@/auth/returnPath.ts'
import { useAuthStore } from '@/store/auth.ts'

export function RequireSession() {
  const session = useAuthStore((state) => state.session)
  const { pathname, search } = useLocation()

  if (session === null) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: sanitizeReturnPath(pathname + search) }}
      />
    )
  }

  return <Outlet />
}
