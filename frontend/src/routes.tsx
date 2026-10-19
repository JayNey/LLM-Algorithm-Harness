import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import type { UserRole } from '@/auth/roles.ts'

export interface AppPage {
  path: string
  label: string
  Component: LazyExoticComponent<ComponentType>
  allowedRoles?: readonly UserRole[]
}

export const appPages: AppPage[] = [
  {
    path: '/',
    label: '仪表盘',
    Component: lazy(() => import('@/pages/Dashboard/DashboardPage.tsx')),
  },
  {
    path: '/problems',
    label: '题目',
    Component: lazy(() => import('@/pages/Problems/ProblemsPage.tsx')),
  },
  {
    path: '/evaluations',
    label: '评估',
    Component: lazy(() => import('@/pages/Evaluations/EvaluationsPage.tsx')),
  },
  {
    path: '/results',
    label: '结果',
    Component: lazy(() => import('@/pages/Results/ResultsPage.tsx')),
  },
  {
    path: '/experiments',
    label: '实验',
    Component: lazy(() => import('@/pages/Experiments/ExperimentsPage.tsx')),
  },
  {
    path: '/settings',
    label: '设置',
    Component: lazy(() => import('@/pages/Settings/SettingsPage.tsx')),
  },
]

export const settingsPages: AppPage[] = [
  {
    path: '/settings/system',
    label: '系统状态',
    allowedRoles: ['admin'],
    Component: lazy(() => import('@/pages/Settings/SystemPage.tsx')),
  },
  {
    path: '/settings/profile',
    label: '个人资料',
    Component: lazy(() => import('@/pages/Settings/ProfilePage.tsx')),
  },
  {
    path: '/settings/api-keys',
    label: 'API 密钥',
    Component: lazy(() => import('@/pages/Settings/ApiKeysPage.tsx')),
  },
]

export const authPages: AppPage[] = [
  {
    path: '/login',
    label: '登录',
    Component: lazy(() => import('@/pages/Auth/LoginPage.tsx')),
  },
  {
    path: '/register',
    label: '注册',
    Component: lazy(() => import('@/pages/Auth/RegisterPage.tsx')),
  },
]
