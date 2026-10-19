import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { RoleContext } from '@/auth/roleContext.ts'
import { createRoleLoader, type RoleState } from '@/auth/roles.ts'
import { useAuthStore } from '@/store/auth.ts'

export function RoleAccess() {
  const [state, setState] = useState<RoleState>({
    status: 'loading',
    role: null,
  })
  const loader = useRef<ReturnType<typeof createRoleLoader> | null>(null)
  useEffect(() => {
    const current = createRoleLoader(
      () => useAuthStore.getState().httpClient().get('/users/me'),
      setState,
    )
    loader.current = current
    void current.load()
    return () => {
      current.dispose()
      loader.current = null
    }
  }, [])
  const reload = useCallback(() => {
    void loader.current?.load()
  }, [])
  return (
    <RoleContext.Provider value={{ state, reload }}>
      <Outlet />
    </RoleContext.Provider>
  )
}
