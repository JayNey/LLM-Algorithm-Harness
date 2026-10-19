import { Alert, Button, Descriptions } from 'antd'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiClientError } from '@/auth/http.ts'
import { useRole } from '@/auth/roleContext.ts'
import { useAuthStore } from '@/store/auth.ts'

type SystemSummary = {
  uptime: number | null
  tasks: number | null
  asyncTasks: number | null
}

function summary(value: unknown): SystemSummary {
  const record =
    typeof value === 'object' && value !== null
      ? (value as Record<string, unknown>)
      : {}
  const number = (key: string) =>
    typeof record[key] === 'number' &&
    Number.isFinite(record[key]) &&
    record[key] >= 0
      ? (record[key] as number)
      : null
  return {
    uptime: number('uptime_seconds'),
    tasks: number('task_count'),
    asyncTasks: number('async_task_count'),
  }
}

export default function SystemPage() {
  const { reload } = useRole()
  const [attempt, setAttempt] = useState(0)
  const [data, setData] = useState<SystemSummary | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const result: unknown = await useAuthStore
          .getState()
          .httpClient()
          .get('/system/status')
        if (active) setData(summary(result))
      } catch (failure) {
        if (!active) return
        if (failure instanceof ApiClientError && failure.status === 403) {
          setError('无权访问此页面')
          reload()
        } else {
          setError('暂时无法获取系统状态，请稍后重试。')
        }
      }
    })()
    return () => {
      active = false
    }
  }, [attempt, reload])
  return (
    <section className="mx-auto w-full max-w-2xl">
      <h1 className="mb-2 text-xl font-semibold">系统状态</h1>
      <p className="mb-6 text-neutral-600 dark:text-neutral-400">
        仅管理员可查看。统计范围为当前 API 进程；两类任务分别展示。
      </p>
      {error ? (
        <Alert
          type="error"
          message={error}
          showIcon
          action={
            <Button
              onClick={() => {
                setError('')
                setData(null)
                setAttempt((value) => value + 1)
              }}
            >
              重试
            </Button>
          }
        />
      ) : data ? (
        <Descriptions
          column={1}
          bordered
          items={[
            {
              key: 'uptime',
              label: '运行时间',
              children:
                data.uptime === null
                  ? '不可用'
                  : `${Math.floor(data.uptime)} 秒`,
            },
            {
              key: 'tasks',
              label: '评估任务数',
              children: data.tasks ?? '不可用',
            },
            {
              key: 'async',
              label: '异步任务数',
              children: data.asyncTasks ?? '不可用',
            },
          ]}
        />
      ) : (
        <p role="status">正在加载系统状态…</p>
      )}
      <p className="mt-6">
        <Link to="/settings">返回设置</Link>
      </p>
    </section>
  )
}
