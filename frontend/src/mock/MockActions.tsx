import { App, Button, Empty, Form, Input, Modal, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
export function MockActions({
  mode,
  onClose,
}: {
  mode: 'create' | 'import' | null
  onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const { message } = App.useApp()
  const navigate = useNavigate()
  useEffect(() => () => clearTimeout(timer.current), [])
  function close() {
    clearTimeout(timer.current)
    setBusy(false)
    onClose()
  }
  return (
    <Modal
      className="harness-modal"
      open={mode !== null}
      title={mode === 'create' ? '创建评估 · Mock' : '导入题目 · Mock'}
      onCancel={close}
      footer={null}
    >
      {mode === 'import' ? (
        <>
          <p>题目导入的交互示例，不读取或上传文件。</p>
          <Empty description="后续接入项目的文件导入服务" />
          <Button
            block
            onClick={() => {
              close()
              navigate('/problems')
              void message.info('已打开题目库示例')
            }}
          >
            查看题目库示例
          </Button>
        </>
      ) : (
        <Form
          layout="vertical"
          onFinish={() => {
            if (busy) return
            setBusy(true)
            timer.current = setTimeout(() => {
              setBusy(false)
              onClose()
              navigate('/evaluations')
              void message.success('示例配置已确认，未提交真实任务')
            }, 450)
          }}
        >
          <p className="muted">验证表单布局与反馈，不会调用模型。</p>
          <Form.Item
            name="name"
            label="评估名称"
            rules={[
              { required: true, whitespace: true, message: '请输入评估名称' },
            ]}
          >
            <Input placeholder="例如：HumanEval 基线对照" />
          </Form.Item>
          <div className="form-grid">
            <Form.Item name="model" label="模型" initialValue="qwen">
              <Select
                options={[
                  { value: 'qwen', label: 'Qwen2.5-Coder-32B' },
                  { value: 'deepseek', label: 'DeepSeek-Coder-V2' },
                ]}
              />
            </Form.Item>
            <Form.Item name="dataset" label="数据集" initialValue="humaneval">
              <Select
                options={[
                  { value: 'humaneval', label: 'HumanEval · 164 题' },
                  { value: 'mbpp', label: 'MBPP · 示例100题' },
                ]}
              />
            </Form.Item>
          </div>
          <Button htmlType="submit" type="primary" loading={busy} block>
            确认示例配置
          </Button>
        </Form>
      )}
    </Modal>
  )
}
