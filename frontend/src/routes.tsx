import { lazy, type ComponentType, type LazyExoticComponent } from 'react'

export interface AppPage {
  path: string
  label: string
  Component: LazyExoticComponent<ComponentType>
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
