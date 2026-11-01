import { useTranslation } from 'react-i18next'
import { currentLanguage, t } from '../../i18n/core.ts'
import { Button, Badge, Drawer, Empty, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useStore } from 'zustand'
import { useAuthStore } from '@/store/auth.ts'
import {
  bindNotificationRefresh,
  createNotificationGateway,
  createNotificationStore,
  notificationHref,
  notificationInstant,
  type AppNotification,
  type NotificationKind,
} from '@/store/notifications.ts'
import { Icon } from './Icon.tsx'

function requestedKind(category: string): NotificationKind | 'all' {
  if (category === '任务完成') return 'task_completed'
  if (category === '预算预警') return 'budget_alert'
  if (category === '系统通知') return 'system'
  return 'all'
}

function kindLabel(kind: NotificationKind): string {
  if (kind === 'task_completed') return t('任务完成')
  if (kind === 'budget_alert') return t('预算预警')
  return t('系统通知')
}

function shownTime(value: string): string {
  const date = notificationInstant(value)
  return Number.isNaN(date.getTime())
    ? t('时间未知')
    : date.toLocaleString(currentLanguage())
}

export function NotificationCenter({ owner }: { owner: string }) {
  useTranslation()

  const [store] = useState(() =>
    createNotificationStore(
      owner,
      createNotificationGateway(useAuthStore.getState().httpClient()),
    ),
  )
  const notes = useStore(store, (state) => state.notes)
  const unread = useStore(store, (state) => state.unread)
  const status = useStore(store, (state) => state.status)
  const nextCursor = useStore(store, (state) => state.nextCursor)
  const load = useStore(store, (state) => state.load)
  const loadMore = useStore(store, (state) => state.loadMore)
  const markRead = useStore(store, (state) => state.markRead)
  const markAllRead = useStore(store, (state) => state.markAllRead)
  const clear = useStore(store, (state) => state.clear)
  const [category, setCategory] = useState('全部')
  const [openedAt, setOpenedAt] = useState<string | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const trigger = useRef<HTMLButtonElement>(null)
  const open = openedAt === location.key
  const wasOpen = useRef(false)
  useEffect(() => {
    if (wasOpen.current && !open) trigger.current?.focus()
    wasOpen.current = open
  }, [open])
  useEffect(() => {
    if (owner === 'anonymous') return
    void load()
    return bindNotificationRefresh(() => {
      void store.getState().load()
    }, window)
  }, [load, owner, store])

  async function openNotification(note: AppNotification) {
    await markRead(note.id)
    if (store.getState().status === 'error') return
    const href = notificationHref(note)
    if (!href) return
    setOpenedAt(null)
    navigate(href)
  }

  return (
    <>
      <Badge count={unread} size="small" offset={[-6, 6]}>
        <Button
          ref={trigger}
          type="text"
          aria-label={t('通知中心，{{value1}} 条未读', { value1: unread })}
          aria-expanded={open}
          onClick={() => {
            setOpenedAt(location.key)
            if (owner !== 'anonymous') void load(requestedKind(category))
          }}
          icon={<Icon name="bell" />}
        />
      </Badge>
      <Drawer
        title={
          <span>
            {t('通知中心')}{' '}
            <small className="muted" role="status">
              {unread} {t(' 条未读')}
            </small>
          </span>
        }
        open={open}
        focusable={{ focusTriggerAfterClose: false }}
        onClose={() => setOpenedAt(null)}
        afterOpenChange={(value) => {
          if (!value) trigger.current?.focus()
        }}
        size={420}
        className="notification-drawer"
      >
        <div className="notification-actions">
          <Button onClick={() => void markAllRead()}>{t('全部已读')}</Button>
          <Button onClick={() => void clear()}>{t('清空通知')}</Button>
        </div>
        <Select
          aria-label={t('通知分类')}
          value={category}
          onChange={(value) => {
            setCategory(value)
            void load(requestedKind(value))
          }}
          options={['全部', '任务完成', '预算预警', '系统通知'].map(
            (value) => ({ value, label: t(value) }),
          )}
          style={{ width: '100%', marginBottom: 20 }}
        />
        {status === 'loading' && notes.length === 0 && (
          <p role="status">{t('正在加载通知')}</p>
        )}
        {status === 'error' && (
          <div role="alert" className="notification-alert">
            <p>{t('通知暂时无法加载')}</p>
            <Button onClick={() => void load(requestedKind(category))}>
              {t('重试')}
            </Button>
          </div>
        )}
        {notes.map((note) => {
          const href = notificationHref(note)
          return (
            <button
              key={note.id}
              className={`notification-item ${note.read ? '' : 'unread'}`}
              onClick={() => void openNotification(note)}
            >
              <div>
                <span className="note-category">
                  {kindLabel(note.kind)}
                  {!note.read ? t(' · 未读') : t(' · 已读')}
                </span>
                <time dateTime={note.createdAt}>
                  {shownTime(note.createdAt)}
                </time>
              </div>
              <strong>{t(note.titleKey, note.params)}</strong>
              <p>{t(note.bodyKey, note.params)}</p>
              <span className="note-link">
                {href ? t('查看详情 ') : t('无法打开该资源')}
                {href ? <Icon name="arrow" size={14} /> : null}
              </span>
            </button>
          )
        })}
        {status === 'ready' && notes.length === 0 && (
          <Empty description={t('这里的通知已处理完毕')} />
        )}
        {nextCursor && (
          <Button onClick={() => void loadMore()} block>
            {t('加载更多')}
          </Button>
        )}
      </Drawer>
    </>
  )
}
