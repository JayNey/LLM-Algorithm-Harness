import type { AxiosInstance } from 'axios'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuthStore } from '../store/auth.ts'
import { createBudgetClient } from './client.ts'
import type { BudgetClient } from './types.ts'

export interface BudgetSession {
  owner: string | null
  client: BudgetClient
}
const SessionContext = createContext<BudgetSession | null>(null)

export function BudgetSessionProvider({ children }: { children: ReactNode }) {
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
  const [session] = useState<BudgetSession>(() => {
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    return { owner, client: createBudgetClient(http) }
  })
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useBudgetSession(): BudgetSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error('预算功能需要会话 provider')
  return session
}
