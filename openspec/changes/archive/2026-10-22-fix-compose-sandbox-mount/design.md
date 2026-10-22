## 修复方案

两份 Compose 的 worker 显式设置 `TMPDIR=${SANDBOX_WORKDIR:-/tmp/llm-harness-sandbox}`，并将同一表达式作为 bind source 与 target。长格式 bind 设置 `create_host_path: false`，目录由部署者提前创建并赋予镜像内 UID/GID 1000 权限。

worker 的 tempfile 与宿主 daemon 读取的是同一目录树；执行器继续为每个用例创建独立随机目录，只读挂载该子目录至沙箱 `/workspace`，运行后按既有逻辑清理。应用源码无需修改。

## 验证

参数化覆盖开发/生产、默认/自定义绝对路径；检查共享目录可写、只挂给 worker；模拟容器路径到宿主路径的映射，使用实际 SandboxExecutor 生成 runner、运行 stdin/stdout 及函数题并检查清理。运行部署与沙箱相关测试、格式与 Compose config 校验。

## 部署约束

在 Docker daemon 所在 Linux 宿主机创建目录，UID/GID 1000，0700。TMPDIR 必须与 source/target 同步；不得将 worker 整个临时目录或共享根目录挂给候选代码。缺少目录时 Compose 拒绝启动；目录不可写时 Python tempfile 可能回退，因此文档提供 writable 断言与 health_check 实测。

## 决策

用户选择独立 hotfix 分支。修复限定于部署配置及其验证，不引入跨模块实现协调；标准 TMPDIR 控制现有 tempfile 行为。Comet 产物语言为 zh-CN。
