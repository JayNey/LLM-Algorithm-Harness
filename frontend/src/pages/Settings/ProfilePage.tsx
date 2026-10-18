import { Alert } from 'antd'
import { useEffect, useState } from 'react'
import { formatUnixSeconds, readProfile } from '@/account/profile.ts'
import { useAuthStore } from '@/store/auth.ts'

export default function ProfilePage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [createdAt, setCreatedAt] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const profile = readProfile(
          await useAuthStore.getState().httpClient().get('/users/me'),
        )
        if (!active) return
        if (!profile) {
          setError('服务暂时不可用')
          return
        }
        setUsername(profile.username)
        setEmail(profile.email)
        setCreatedAt(profile.created_at)
      } catch {
        if (!active) return
        setError('服务暂时不可用')
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  if (loading) return <p>加载中</p>
  if (error || createdAt === null) {
    return (
      <section>
        <h1>个人资料</h1>
        <Alert type="error" message={error || '服务暂时不可用'} showIcon />
      </section>
    )
  }

  return (
    <section>
      <h1>个人资料</h1>
      <p>用户名：{username}</p>
      <p>邮箱：{email}</p>
      <p>注册时间：{formatUnixSeconds(createdAt)}</p>
    </section>
  )
}
