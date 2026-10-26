import { App, Button, Empty, Modal } from 'antd'
import { useNavigate } from 'react-router-dom'
export function MockActions({
  mode,
  onClose,
}: {
  mode: 'import' | null
  onClose: () => void
}) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  return (
    <Modal
      className="harness-modal"
      open={mode !== null}
      title="导入题目 · Mock"
      onCancel={onClose}
      footer={null}
    >
      <p>题目导入的交互示例，不读取或上传文件。</p>
      <Empty description="后续接入项目的文件导入服务" />
      <Button
        block
        onClick={() => {
          onClose()
          navigate('/problems')
          void message.info('已打开题目库示例')
        }}
      >
        查看题目库示例
      </Button>
    </Modal>
  )
}
