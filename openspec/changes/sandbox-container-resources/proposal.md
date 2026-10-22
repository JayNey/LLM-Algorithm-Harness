## Why

#226/#229/#232 前置未满足，#157 已有依赖均已合并 main，可继续其独立的 Docker 容器资源观测。目前 system/status.containers 为占位，沙箱也没有可区分于其他容器的固定管理标签。

## What Changes

- 新建沙箱加入固定版本管理标签；管理员可显式启用仅针对该标签的只读 Docker ps/stats 采样。
- 返回匿名容器 ID、CPU/内存/PIDs 数值，设置总预算、输出和样本上限、并发去重、缓存和关闭清理。
- 不暴露名称、镜像、命令、挂载、环境或原始异常；无测量保留 null。补真实 Docker 验证、独立审查及文档。

## Capabilities

### New Capabilities
- `api/container-resources`：当前 API 进程 Docker context 中有标签沙箱的有限资源快照。

### Modified Capabilities
无。保留现有系统状态路由和认证、沙箱权限/资源限制。

## Impact

单一增量 Tweak，复用现有进程树超时/输出限制工具，不引入 Docker SDK、数据库迁移或新端点。不领取其他负责人的 #224/#225；#157 的 LLM/配额等剩余范围保持开放。
