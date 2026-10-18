import { Link } from 'react-router-dom'

export default function SettingsPage() {
  return (
    <section>
      <h1>设置</h1>
      <p>
        <Link to="/settings/profile">个人资料</Link>
      </p>
      <p>
        <Link to="/settings/api-keys">API 密钥</Link>
      </p>
    </section>
  )
}
