import type { AxiosInstance } from 'axios'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuthStore } from '../store/auth.ts'
import { createSystemLogClient } from './client.ts'
import type { SystemLogClient } from './types.ts'

export interface SystemLogSession {
  owner: string | null
  client: SystemLogClient
}
const SessionContext = createContext<SystemLogSession | null>(null)

export function SystemLogSessionProvider({
  children,
}: {
  children: ReactNode
}) {
  const owner = useAuthStore((state) => state.session?.marker ?? null)
  return (
    <SessionScope key={owner ?? 'anonymous'} owner={owner}>
      {children}
    </SessionScope>
  )
}
function SessionScope({
  owner,
  children,
}: {
  owner: string | null
  children: ReactNode
}) {
  const [session] = useState<SystemLogSession>(() => {
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    return { owner, client: createSystemLogClient(http) }
  })
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSystemLogSession(): SystemLogSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error('系统日志功能需要会话 provider')
  return session
}
