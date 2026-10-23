import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import type { UserRole } from '@/auth/roles.ts'

export interface AppPage {
  path: string
  label: string
  Component: LazyExoticComponent<ComponentType>
  allowedRoles?: readonly UserRole[]
  group?: string
  icon?:
    | 'grid'
    | 'code'
    | 'play'
    | 'chart'
    | 'flask'
    | 'layers'
    | 'pulse'
    | 'settings'
    | 'help'
}

export const appPages: AppPage[] = [
  {
    path: '/',
    group: '评估工作台',
    icon: 'grid',
    label: '仪表盘',
    Component: lazy(() => import('@/pages/Dashboard/DashboardPage.tsx')),
  },
  {
    path: '/problems',
    group: '评估工作台',
    icon: 'code',
    label: '题目库',
    Component: lazy(() => import('@/pages/Problems/ProblemsPage.tsx')),
  },
  {
    path: '/evaluations',
    group: '评估工作台',
    icon: 'play',
    label: '评估任务',
    Component: lazy(() => import('@/pages/Evaluations/EvaluationsPage.tsx')),
  },
  {
    path: '/results',
    group: '分析与对比',
    icon: 'chart',
    label: '评估结果',
    Component: lazy(() => import('@/pages/Results/ResultsPage.tsx')),
  },
  {
    path: '/experiments',
    group: '分析与对比',
    icon: 'flask',
    label: '实验',
    Component: lazy(() => import('@/pages/Experiments/ExperimentsPage.tsx')),
  },
  {
    path: '/benchmarks',
    label: '基准测试',
    group: '分析与对比',
    icon: 'layers',
    Component: lazy(() => import('@/mock/BusinessPage.tsx')),
  },
  {
    path: '/help',
    label: '帮助文档',
    group: '系统',
    icon: 'help',
    Component: lazy(() => import('@/mock/BusinessPage.tsx')),
  },
  {
    path: '/settings',
    group: '系统',
    icon: 'settings',
    label: '设置',
    Component: lazy(() => import('@/pages/Settings/SettingsPage.tsx')),
  },
]

export const settingsPages: AppPage[] = [
  {
    path: '/settings/system',
    group: '系统',
    icon: 'pulse',
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

export const detailPages: AppPage[] = [
  {
    path: '/evaluations/new',
    label: '创建评估',
    Component: lazy(
      () => import('@/pages/Evaluations/CreateEvaluationPage.tsx'),
    ),
  },
  {
    path: '/evaluations/:evaluationId',
    label: '评估任务详情',
    Component: lazy(
      () => import('@/pages/Evaluations/EvaluationDetailPage.tsx'),
    ),
  },
  {
    path: '/experiments/new',
    label: '创建实验',
    Component: lazy(
      () => import('@/pages/Experiments/CreateExperimentPage.tsx'),
    ),
  },
  {
    path: '/experiments/:experimentId',
    label: '实验详情',
    Component: lazy(
      () => import('@/pages/Experiments/ExperimentDetailPage.tsx'),
    ),
  },
]
