import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Badge, Button, Drawer, Empty, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useStore } from 'zustand'
import { createNotificationStore } from '@/store/notifications.ts'
import { Icon } from './Icon.tsx'
export function NotificationCenter({ owner }: { owner: string }) {
  useTranslation()

  const [store] = useState(() => createNotificationStore(owner))
  const { notes, markRead, markAllRead, clear } = useStore(store)
  const [category, setCategory] = useState('全部')
  const [openedAt, setOpenedAt] = useState<string | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const trigger = useRef<HTMLButtonElement>(null)
  const unread = notes.filter((n) => !n.read).length
  const visible = notes.filter(
    (n) => category === '全部' || n.type === category,
  )
  const open = openedAt === location.key
  // Restore focus even when a rapid close skips the animation callback.
  const wasOpen = useRef(false)
  useEffect(() => {
    if (wasOpen.current && !open) trigger.current?.focus()
    wasOpen.current = open
  }, [open])
  return (
    <>
      <Badge count={unread} size="small" offset={[-6, 6]}>
        <Button
          ref={trigger}
          type="text"
          aria-label={t('通知中心，{{value1}} 条未读', { value1: unread })}
          aria-expanded={open}
          onClick={() => setOpenedAt(location.key)}
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
          <Button onClick={markAllRead}>{t('全部已读')}</Button>
          <Button onClick={clear}>{t('清空通知')}</Button>
        </div>
        <Select
          aria-label={t('通知分类')}
          value={category}
          onChange={setCategory}
          options={['全部', '任务完成', '预算预警', '系统通知'].map(
            (value) => ({ value, label: t(value) }),
          )}
          style={{ width: '100%', marginBottom: 20 }}
        />
        {visible.map((n) => (
          <button
            key={n.id}
            className={`notification-item ${n.read ? '' : 'unread'}`}
            onClick={() => {
              markRead(n.id)
              setOpenedAt(null)
              navigate(n.route)
            }}
          >
            <div>
              <span className="note-category">
                {t(n.type)}
                {!n.read ? t(' · 未读') : t(' · 已读')}
              </span>
              <time>{n.time}</time>
            </div>
            <strong>{t(n.title)}</strong>
            <p>{t(n.text)}</p>
            <span className="note-link">
              {t('查看详情 ')}
              <Icon name="arrow" size={14} />
            </span>
          </button>
        ))}
        {visible.length === 0 && (
          <Empty description={t('这里的通知已处理完毕')} />
        )}
        <p className="sample-caption">
          {t('Mock 通知 · 本次会话内保存，不会发送真实消息。')}
        </p>
      </Drawer>
    </>
  )
}
