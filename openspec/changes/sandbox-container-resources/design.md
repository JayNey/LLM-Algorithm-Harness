## 实现

SandboxExecutor 的 Docker 命令增加固定非敏感 label，API 仅以相同 selector 查询正在运行的容器。容器标签是观测筛选器，不是资源所有者认证；仅管理员接口可访问。旧版无标签容器不统计，API Docker context 可能与远端 worker 不同，响应明确限定范围。

ContainerProbes 使用已有 run_bounded 执行固定 docker ps 与 docker stats --no-stream，两个命令分享单次时间预算，每命令合计 stdout/stderr 最多64KiB，最多采样64个容器（默认32）。只请求格式化数值和 ID，验证 ID 属于筛选结果后取摘要，不接受任意命令或 HTTP 指定过滤器。

CLI 的舍入字节和百分数按其真实显示语义转换；缺失/平台不支持/非法字段为 null，退出或消失为部分观测，不填假零。无匹配有标签运行容器的成功 inventory 才允许真实空列表。返回 listed_count、sampled_count、truncated 及每行状态，不生成全局 CPU/内存汇总。

每 API 进程仅一个采样；成功/失败均按 TTL 缓存并标记年龄，过期并发请求不取旧成功值。关闭标记 closed 并等待已有有界命令结束（含最多12秒清理余量（复用进程工具的两个 pipe join 各最多5秒，并留调度余量）），不再开始新采样。只读观测不启动、停止或 inspect 任意业务容器。

## 验证

先验证现有 Docker 命令缺少标签的 RED。单测覆盖命令白名单、单位、异常/非有限数值、缺失/重复/外国ID、超页样本、总预算、输出限制、负缓存、并发与关闭、公开/401/403 零探测，以及现有 API 契约和 sandbox 回归。真实 Docker 用新建的两个受限测试容器，一有标签一无标签，验证资源与筛选后仅清理这两个容器。普通测试不依赖 Docker daemon。

## 流程与边界

继续已确认的 Tweak/分支方式，单一 #157 子范围不改架构。Docker Linux CLI 内存会扣除部分缓存，Windows daemon 部分列不可用，文档按官方 stats 协议标明；主机/生产集群和供应商联调不外推。
