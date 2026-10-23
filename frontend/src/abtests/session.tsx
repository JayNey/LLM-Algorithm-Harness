import type { AxiosInstance } from 'axios'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuthStore } from '../store/auth.ts'
import { createABTestClient } from './client.ts'
import type { ABTestClient } from './types.ts'

export interface ABTestSession {
  owner: string | null
  client: ABTestClient
}
const SessionContext = createContext<ABTestSession | null>(null)

export function ABTestSessionProvider({ children }: { children: ReactNode }) {
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
  const [session] = useState<ABTestSession>(() => {
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    return { owner, client: createABTestClient(http) }
  })
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useABTestSession(): ABTestSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error('AB 测试功能需要会话 provider')
  return session
}
