# Issue #168 · 工作台设计与实现说明

版本：2026-10-20。三套风格和 Frontier SVG 已获用户确认并接入 `frontend/`，本文描述当前仓库实现。业务与通知为本地 Mock；认证、角色守卫、个人资料、API 密钥和登出复用已有实现。

视觉系统的规范快照见 [frontend/DESIGN.md](../../frontend/DESIGN.md)，面板扩展数据见 [design.json](../../frontend/.impeccable/design.json)。实现 token 权威是 [appearance.ts](../../frontend/src/layouts/appearance.ts) 与 [shell.css](../../frontend/src/layouts/shell.css)，不能只修改文档而让两套实现分叉。

## 设计方向与品牌

Frontier 的三个斜向切片代表候选解，下方折线表达成本与准确率权衡的效率前沿，是品牌隐喻。主资产位于 `frontend/public/brand/harness-frontier.svg`，单色资产为同目录 `harness-frontier-mono.svg`。侧栏、折叠导航、手机顶栏、抽屉与 favicon 复用品牌资产；应用名来自现有环境配置；默认完整名称 `LLM Algorithm Harness` 在侧栏与手机使用 `Harness` 紧凑字标，完整名称仍保留在 title 与可访问名称中；其他配置名称直接显示其原值。

Orbit 是关注运行与恢复的深空控制台，Precision 是关注基准与比较的精密实验室，Studio 是关注实验与记录的石墨工作室。三者具有各自的首屏构图、侧栏密度、形状与浅深配色；均使用 React、AntD 和现有系统字体栈，不引入新的组件库或字体请求。它们现在是可切换的实现，不再是待选择的独立原型。

## 信息与业务示例

首页优先回答哪些评估正在运行、哪些失败需要处理、哪些结果可以比较。内容来自 `frontend/src/mock/data.ts`：4 个任务（1 运行、2 完成、1 失败），示例费用 $4.84；已完成任务共 328 道题，249 道通过，整体 Pass@1 为 75.9%。比较仅使用同为 HumanEval / Direct 的已完成任务；显示值差为 4.2 个百分点。未完成任务不展示最终 Pass@1。这些数字仅为布局与交互样例，不代表真实模型性能或当前服务状态。

任务搜索、状态筛选、任务详情、创建配置、导入与失败恢复演示位于 `frontend/src/mock/`。创建表单验证名称，模型与数据集有默认选项，确认后短时加载并明确提示未提交真实任务；导入不读取或上传文件；恢复不向后端发任务。帮助页提供成功、错误、警告、信息四类可关闭 Toast。

## 外壳与交互

`AppLayout.tsx` 挂载 ConfigProvider、AntD App、侧栏、顶栏、main、手机导航、抽屉与公共 Mock 操作。布局不以风格为 React key；即时切换不会重新加载页面或卸载 Outlet。`main.tsx` 订阅 UI store，同步根元素 `data-design`、`data-theme` 和 `dark` class，并监听系统深色变化。

风格与主题选择器位于外壳，每种风格分别保存 `light/dark/system` 偏好；默认 Orbit 深色，Precision 与 Studio 浅色。顶栏主题按钮将当前模式切到显式浅色或深色，选择器可恢复跟随系统。手机选择区额外显示“业务与通知 · Mock”；六套模式的输入占位文字与辅助文字使用同一颜色映射。`llm-harness-ui` 在 localStorage 保存风格、三套主题偏好、桌面侧栏折叠；存储不可用时继续使用内存状态。不写入 URL 风格参数。UI 偏好为浏览器级，并非用户服务端配置。

导航与通知面板按当前 location key 开启，路由变化后关闭；导航后 main 聚焦。抽屉关闭回到触发按钮。折叠导航保留标签和 Tooltip；页面提供跳至正文链接、面包屑与当前项语义。手机常用导航是仪表盘、题目库、评估、结果；完整分组在抽屉中。

通知使用当前 session marker 创建的内存 store，换会话 marker 时重建；外观切换不重建通知。支持未读计数、分类、单条与全部已读、清空及限定的站内跳转。刷新恢复初始种子，不做 localStorage 持久化、跨标签或跨设备同步。这里没有通知后端或 WebSocket 接入。

Loading、EmptyState、ErrorState、ErrorBoundary 与 Toast 示例位于 `frontend/src/components/common/Feedback.tsx`。页面演示状态可切正常、加载、空、错误；模拟错误重试经过短暂加载后回正常。真实 React ErrorBoundary 捕获 Outlet 渲染异常，并随路径重置；它与演示错误状态不同。

## 响应式与验收边界

最小验收宽度为 320px；768px 以下使用手机导航与任务卡片，768–1023px 使用抽屉而无底部导航，1024–1279px 使用 200px 桌面侧栏与下置辅助区，1280px 起使用完整风格列宽，1440px 为桌面验收视口。1440px 没有独立 CSS 断点；1536px 起有额外大屏留白规则。完整尺寸与形状规则见设计系统 Layout。

手机主要触控目标按 CSS 放大到 44px；通知全宽、Modal 全屏、表单双列转单列，底部预留导航与 safe area 空间。颜色过渡避免布局动画。`prefers-reduced-motion: reduce` 通过响应式订阅把 AntD `token.motion` 设为 `false`，避免浮层在动画初始缩放态定位；其余自定义动画时长缩短为 0.01ms、关闭过渡、动画迭代次数设为 1，并关闭顺滑滚动，以保留 AntD 浮层关闭所需的结束事件；自有 DesignFocus 动画仍直接禁用。

验证状态和限制另见 [QA.md](QA.md)。无论自动化报告如何，模拟浏览器视口都不能替代真实设备、Safari/Firefox、屏幕阅读器、触摸输入及真实后端会话验证；本文不声称这些项目已通过。
