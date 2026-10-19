import { createContext, useContext } from 'react'
import type { RoleState } from './roles.ts'

export const RoleContext = createContext<{
  state: RoleState
  reload: () => void
}>({ state: { status: 'loading', role: null }, reload: () => {} })

export function useRole() {
  return useContext(RoleContext)
}
