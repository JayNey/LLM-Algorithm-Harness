import assert from 'node:assert/strict'
import { test } from 'node:test'
import enUS from './en-US.ts'
import zhCN from './zh-CN.ts'

const help =
  '顶部通知中心保存当前账号的任务完成和预算阈值预警，刷新或重新登录后仍然可见。'
const budget =
  '预警由 Web 评估 worker 在启动、恢复和成本结算时检查，需要个人全局预算及启用的规则。保存规则不会立即发送，也不代表投递成功；其他任务类型不会独立触发检查。Slack/Webhook 使用规则中的 HTTPS 目标；邮件需要部署方配置 worker 的 COST_ALERT_SMTP_*。达到阈值时站内通知单独记录，外部渠道发送成功或失败不改变这条站内预警。'

test('帮助和预算文案不再把站内通知写成示例', () => {
  for (const catalog of [zhCN, enUS]) {
    assert.equal(catalog[help]?.includes('示例'), false)
    assert.equal(/mock/i.test(catalog[help] ?? ''), false)
    assert.equal(catalog[budget]?.includes('Mock'), false)
    assert.equal(
      Object.hasOwn(
        catalog,
        '顶部通知中心的内容仍为示例数据，不反映真实任务事件。',
      ),
      false,
    )
    assert.equal(
      Object.hasOwn(catalog, 'Mock 通知 · 本次会话内保存，不会发送真实消息。'),
      false,
    )
  }
  assert.match(enUS[help] ?? '', /current account/)
  assert.match(enUS[budget] ?? '', /separate in-app notification/)
  assert.match(zhCN[budget] ?? '', /外部渠道发送成功或失败不改变/)
})
