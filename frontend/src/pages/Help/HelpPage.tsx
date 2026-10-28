import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import '@/evaluations/workflow.css'

const sections = [
  { id: 'keys', title: '密钥配置' },
  { id: 'problems', title: '题库导入' },
  { id: 'evaluations', title: '创建与启动评估' },
  { id: 'results', title: '查看结果与报告' },
  { id: 'experiments', title: '实验、基准与 A/B 测试' },
  { id: 'budgets', title: '预算与通知' },
  { id: 'admin', title: '管理员与运行环境' },
] as const

export default function HelpPage() {
  useTranslation()
  const navigate = useNavigate()
  return (
    <section className="evaluation-workflow help-guide">
      <header className="page-heading">
        <div>
          <h1>{t('帮助文档')}</h1>
          <p>
            {t(
              '按真实流程完成一次评估：配置密钥、导入题目、创建并启动任务、查看结果。',
            )}
          </p>
        </div>
        <div className="page-actions">
          <Button type="primary" onClick={() => navigate('/evaluations/new')}>
            {t('创建评估')}
          </Button>
        </div>
      </header>
      <nav className="panel evaluation-panel" aria-label={t('帮助目录')}>
        <ol>
          {sections.map((section) => (
            <li key={section.id}>
              <a href={`#help-${section.id}`}>{t(section.title)}</a>
            </li>
          ))}
        </ol>
      </nav>
      <div className="panel evaluation-panel">
        <section id="help-keys" aria-labelledby="help-keys-title">
          <h2 id="help-keys-title">1. {t('密钥配置')}</h2>
          <ol>
            <li>
              {t('在')}
              <Link to="/settings/api-keys">{t('设置 → API 密钥')}</Link>
              {t(
                '添加模型提供商的密钥。密钥加密存储，界面只显示脱敏预览；创建评估时按密钥读取可用模型目录。',
              )}
            </li>
            <li>
              {t('在')}
              <Link to="/settings/pricing">{t('设置 → 定价管理')}</Link>
              {t(
                '为使用的模型配置每 1k tokens 的输入/输出单价；未配置定价的模型成本按未知处理，不计入费用统计。',
              )}
            </li>
          </ol>
        </section>
        <section id="help-problems" aria-labelledby="help-problems-title">
          <h2 id="help-problems-title">2. {t('题库导入')}</h2>
          <ol>
            <li>
              {t('进入')}
              <Link to="/problems">{t('题目库')}</Link>
              {t(
                '，选择题目文件后导入：小文件同步直导，大文件后台异步导入并显示进度与校验报告；可选择追加或覆盖。',
              )}
            </li>
            <li>
              {t(
                '侧栏与快速操作中的「导入题目」目前仍是示例交互，不读取文件；真实导入请在题库页完成。',
              )}
            </li>
          </ol>
        </section>
        <section id="help-evaluations" aria-labelledby="help-evaluations-title">
          <h2 id="help-evaluations-title">3. {t('创建与启动评估')}</h2>
          <ol>
            <li>
              {t('打开')}
              <Link to="/evaluations/new">{t('创建评估')}</Link>
              {t(
                '，依次选择密钥、模型（按密钥读取目录，也可手动输入）、策略与题目，创建后立即请求启动。',
              )}
            </li>
            <li>
              {t('在')}
              <Link to="/evaluations">{t('评估任务')}</Link>
              {t(
                '查看任务状态与花费；详情页通过实时通道推送进度，连接不可用时自动切换为轮询。',
              )}
            </li>
            <li>
              {t(
                '任务执行依赖后端的 Redis、Celery worker 与 Docker 沙箱镜像；缺少任一组件时启动会被拒绝或在预检阶段失败，错误原因会显示在任务页。',
              )}
            </li>
          </ol>
        </section>
        <section id="help-results" aria-labelledby="help-results-title">
          <h2 id="help-results-title">4. {t('查看结果与报告')}</h2>
          <ol>
            <li>
              {t('在')}
              <Link to="/results">{t('评估结果')}</Link>
              {t(
                '查看策略汇总与单题结果；结果页区分等待结果、部分缺失、失败与完整等状态，不把部分记录当作完整评估。',
              )}
            </li>
            <li>
              {t(
                '结果详情的报告下载入口尚未提供；后端已支持 Markdown、HTML 与 CSV 即时报告接口，可在界面接入前通过 API 获取。',
              )}
            </li>
          </ol>
        </section>
        <section id="help-experiments" aria-labelledby="help-experiments-title">
          <h2 id="help-experiments-title">5. {t('实验、基准与 A/B 测试')}</h2>
          <ol>
            <li>
              <Link to="/experiments/new">{t('实验')}</Link>
              {t('、')}
              <Link to="/benchmarks">{t('基准测试')}</Link>
              {t('与')}
              <Link to="/ab-tests/new">{t('A/B 测试')}</Link>
              {t(
                '的数据集路径须填写 DATA_ROOT 下的相对路径（如 datasets/demo.json），而不是题库中的题目。',
              )}
            </li>
            <li>
              {t(
                '三处表单的模型与策略可直接从目录选择：策略来自评估选项，模型按所选密钥读取；目录加载失败或不完整时仍可手动输入。',
              )}
            </li>
          </ol>
        </section>
        <section id="help-budgets" aria-labelledby="help-budgets-title">
          <h2 id="help-budgets-title">6. {t('预算与通知')}</h2>
          <ol>
            <li>
              {t('在')}
              <Link to="/settings/budgets">{t('设置 → 预算与预警')}</Link>
              {t(
                '设置个人预算；预算用于控制评估任务的暂停与策略降级，实验、基准与 A/B 任务不受其约束。',
              )}
            </li>
            <li>
              {t(
                '预警投递支持 Slack、Webhook 与 SMTP 邮件，依赖部署时的渠道配置；保存规则不等于投递成功。',
              )}
            </li>
            <li>{t('顶部通知中心的内容仍为示例数据，不反映真实任务事件。')}</li>
          </ol>
        </section>
        <section id="help-admin" aria-labelledby="help-admin-title">
          <h2 id="help-admin-title">7. {t('管理员与运行环境')}</h2>
          <ol>
            <li>
              <Link to="/settings/system">{t('设置 → 系统状态')}</Link>
              {t(
                '仅管理员可见：由部署者在后端 MONITOR_ADMIN_USER_IDS 中配置已注册用户的 UUID 并重启 API，没有自助提权入口。',
              )}
            </li>
            <li>
              {t(
                '本地运行方式与环境变量说明见仓库 docs/deployment/deploy.md；界面语言可在右上角切换，偏好会被保存。',
              )}
            </li>
          </ol>
        </section>
      </div>
    </section>
  )
}
