import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { LanguageSelect } from '@/i18n/LocaleProvider.tsx'
import { Button, ConfigProvider } from 'antd'
import { Navigate, Outlet } from 'react-router-dom'
import { readViteEnv } from '@/config/env.ts'
import { useAuthStore } from '@/store/auth.ts'
import { useUiStore } from '@/store/ui.ts'
import { appearanceTheme } from './appearance.ts'
import './auth-entry.css'

const appName = readViteEnv().appName

function FrontierIllustration() {
  return (
    <figure className="auth-frontier-chart">
      <svg viewBox="0 0 510 238" role="img" aria-label={t('成本与准确率')}>
        <defs>
          <pattern
            id="auth-frontier-grid"
            x="35"
            y="25"
            width="54"
            height="36"
            patternUnits="userSpaceOnUse"
          >
            <path d="M0 36V0H54" className="auth-chart-grid" fill="none" />
          </pattern>
          <linearGradient id="auth-frontier-area" x2="0" y2="1">
            <stop stopColor="var(--accent)" stopOpacity=".15" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M35 25H487V205H35Z" fill="url(#auth-frontier-grid)" />
        <path
          d="M35 174H123V135H207V97H311V63H401V42H481V205H35Z"
          fill="url(#auth-frontier-area)"
        />
        <path d="M35 25V205H487" stroke="var(--control)" fill="none" />
        <path
          d="M35 174H123V135H207V97H311V63H401V42H481"
          stroke="var(--accent)"
          strokeWidth="2"
          fill="none"
        />
        <path
          d="m123 129 6 6-6 6-6-6Z M207 91l6 6-6 6-6-6Z M311 57l6 6-6 6-6-6Z M401 36l6 6-6 6-6-6Z"
          fill="var(--accent)"
          stroke="var(--surface)"
          strokeWidth="2"
        />
        <g fill="var(--control)">
          <circle cx="69" cy="188" r="3" />
          <circle cx="106" cy="181" r="3" />
          <circle cx="161" cy="162" r="3.5" />
          <circle cx="224" cy="176" r="3" />
          <circle cx="248" cy="121" r="3.5" />
          <circle cx="279" cy="142" r="3" />
          <circle cx="338" cy="111" r="3" />
          <circle cx="368" cy="85" r="3.5" />
          <circle cx="420" cy="130" r="3" />
          <circle cx="433" cy="86" r="3" />
          <circle cx="462" cy="67" r="3.5" />
        </g>
        <g fill="var(--muted)" fontSize="11">
          <text x="35" y="14">
            {t('准确率')}
          </text>
          <text x="487" y="225" textAnchor="end">
            {t('评估成本')}
          </text>
          <text x="481" y="29" textAnchor="end" fill="var(--accent)">
            {t('效率前沿')}
          </text>
        </g>
      </svg>
      <figcaption>{t('概念示意')}</figcaption>
    </figure>
  )
}

export function AuthLayout() {
  useTranslation()

  const session = useAuthStore((state) => state.session)
  const colorScheme = useUiStore((state) => state.colorScheme)
  const toggleColorScheme = useUiStore((state) => state.toggleColorScheme)

  if (session !== null) {
    return <Navigate to="/" replace />
  }

  const dark = colorScheme === 'dark'
  const frontierTheme = appearanceTheme('orbit', colorScheme)

  return (
    <ConfigProvider
      theme={{
        ...frontierTheme,
        token: {
          ...frontierTheme.token,
          colorBgContainer: dark ? '#111e30' : '#fff',
          controlHeight: 44,
        },
        components: {
          Button: { primaryColor: dark ? '#101c2c' : '#fff' },
          Form: { itemMarginBottom: 18 },
        },
      }}
    >
      <div className="auth-entry" data-scheme={colorScheme}>
        <header className="auth-entry-header">
          <div className="auth-entry-brand">
            <img
              src="/brand/harness-frontier.svg"
              alt=""
              width="28"
              height="28"
            />
            <strong>{appName}</strong>
          </div>
          <div className="auth-entry-settings">
            <LanguageSelect />
            <Button
              type="text"
              aria-label={dark ? t('切换至浅色') : t('切换至深色')}
              onClick={toggleColorScheme}
            >
              {dark ? t('浅色') : t('深色')}
            </Button>
          </div>
        </header>
        <div className="auth-entry-layout">
          <aside className="auth-entry-intro">
            <p className="auth-entry-headline">
              <span>{t('解法各异，')}</span>
              <span>{t('取舍有据。')}</span>
            </p>
            <p className="auth-entry-description">
              {t('在同一组题目上衡量模型的准确率与评估成本。')}
            </p>
            <FrontierIllustration />
          </aside>
          <main className="auth-entry-main">
            <Outlet />
          </main>
        </div>
      </div>
    </ConfigProvider>
  )
}
