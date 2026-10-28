import { t } from './i18n/core.ts'
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
    get label() {
      return t('仪表盘')
    },
    Component: lazy(() => import('@/pages/Dashboard/DashboardPage.tsx')),
  },
  {
    path: '/problems',
    group: '评估工作台',
    icon: 'code',
    get label() {
      return t('题目库')
    },
    Component: lazy(() => import('@/pages/Problems/ProblemsPage.tsx')),
  },
  {
    path: '/evaluations',
    group: '评估工作台',
    icon: 'play',
    get label() {
      return t('评估任务')
    },
    Component: lazy(() => import('@/pages/Evaluations/EvaluationsPage.tsx')),
  },
  {
    path: '/results',
    group: '分析与对比',
    icon: 'chart',
    get label() {
      return t('评估结果')
    },
    Component: lazy(() => import('@/pages/Results/ResultsPage.tsx')),
  },
  {
    path: '/experiments',
    group: '分析与对比',
    icon: 'flask',
    get label() {
      return t('实验')
    },
    Component: lazy(() => import('@/pages/Experiments/ExperimentsPage.tsx')),
  },
  {
    path: '/benchmarks',
    get label() {
      return t('基准测试')
    },
    group: '分析与对比',
    icon: 'layers',
    Component: lazy(() => import('@/pages/Benchmarks/BenchmarksPage.tsx')),
  },
  {
    path: '/ab-tests',
    get label() {
      return t('A/B 测试')
    },
    group: '分析与对比',
    icon: 'pulse',
    Component: lazy(() => import('@/pages/ABTests/ABTestsPage.tsx')),
  },
  {
    path: '/help',
    get label() {
      return t('帮助文档')
    },
    group: '系统',
    icon: 'help',
    Component: lazy(() => import('@/pages/Help/HelpPage.tsx')),
  },
  {
    path: '/settings',
    group: '系统',
    icon: 'settings',
    get label() {
      return t('设置')
    },
    Component: lazy(() => import('@/pages/Settings/SettingsPage.tsx')),
  },
]

export const settingsPages: AppPage[] = [
  {
    path: '/settings/system',
    group: '系统',
    icon: 'pulse',
    get label() {
      return t('系统状态')
    },
    allowedRoles: ['admin'],
    Component: lazy(() => import('@/pages/Settings/SystemPage.tsx')),
  },
  {
    path: '/settings/logs',
    group: '系统',
    get label() {
      return t('系统日志')
    },
    allowedRoles: ['admin'],
    Component: lazy(() => import('@/pages/Settings/SystemLogsPage.tsx')),
  },
  {
    path: '/settings/profile',
    get label() {
      return t('个人资料')
    },
    Component: lazy(() => import('@/pages/Settings/ProfilePage.tsx')),
  },
  {
    path: '/settings/api-keys',
    get label() {
      return t('API 密钥')
    },
    Component: lazy(() => import('@/pages/Settings/ApiKeysPage.tsx')),
  },
  {
    path: '/settings/budgets',
    get label() {
      return t('预算与预警')
    },
    Component: lazy(() => import('@/pages/Settings/BudgetsPage.tsx')),
  },
  {
    path: '/settings/pricing',
    get label() {
      return t('定价管理')
    },
    Component: lazy(() => import('@/pages/Settings/PricingPage.tsx')),
  },
]

export const authPages: AppPage[] = [
  {
    path: '/login',
    get label() {
      return t('登录')
    },
    Component: lazy(() => import('@/pages/Auth/LoginPage.tsx')),
  },
  {
    path: '/register',
    get label() {
      return t('注册')
    },
    Component: lazy(() => import('@/pages/Auth/RegisterPage.tsx')),
  },
]

export const detailPages: AppPage[] = [
  {
    path: '/results/:evaluationId',
    get label() {
      return t('评估结果详情')
    },
    Component: lazy(() => import('@/pages/Results/ResultDetailPage.tsx')),
  },
  {
    path: '/evaluations/new',
    get label() {
      return t('创建评估')
    },
    Component: lazy(
      () => import('@/pages/Evaluations/CreateEvaluationPage.tsx'),
    ),
  },
  {
    path: '/evaluations/:evaluationId',
    get label() {
      return t('评估任务详情')
    },
    Component: lazy(
      () => import('@/pages/Evaluations/EvaluationDetailPage.tsx'),
    ),
  },
  {
    path: '/experiments/new',
    get label() {
      return t('创建实验')
    },
    Component: lazy(
      () => import('@/pages/Experiments/CreateExperimentPage.tsx'),
    ),
  },
  {
    path: '/experiments/:experimentId',
    get label() {
      return t('实验详情')
    },
    Component: lazy(
      () => import('@/pages/Experiments/ExperimentDetailPage.tsx'),
    ),
  },
  {
    path: '/benchmarks/:suiteId',
    get label() {
      return t('基准套件详情')
    },
    Component: lazy(() => import('@/pages/Benchmarks/BenchmarkDetailPage.tsx')),
  },
  {
    path: '/ab-tests/new',
    get label() {
      return t('创建 A/B 测试')
    },
    Component: lazy(() => import('@/pages/ABTests/CreateABTestPage.tsx')),
  },
  {
    path: '/ab-tests/:testId',
    get label() {
      return t('A/B 测试详情')
    },
    Component: lazy(() => import('@/pages/ABTests/ABTestDetailPage.tsx')),
  },
]
