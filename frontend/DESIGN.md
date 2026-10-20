---
name: LLM Algorithm Harness
description: Frontier 品牌下可即时切换的 Orbit、Precision、Studio 算法评估工作台
colors:
  orbit-light-frame: '#e9f0f7'
  orbit-light-bg: '#f8fbff'
  orbit-light-surface: '#edf3fa'
  orbit-light-text: '#172b41'
  orbit-light-muted: '#50677f'
  orbit-light-line: '#d5e0ed'
  orbit-light-control: '#7d91a8'
  orbit-light-accent: '#2168b0'
  orbit-light-accent-soft: '#e0efff'
  orbit-dark-frame: '#0b1320'
  orbit-dark-bg: '#101c2c'
  orbit-dark-surface: '#16263a'
  orbit-dark-text: '#e5effa'
  orbit-dark-muted: '#a4b7cc'
  orbit-dark-line: '#293b51'
  orbit-dark-control: '#6b84a0'
  orbit-dark-accent: '#7bcaff'
  orbit-dark-accent-soft: '#213e58'
  orbit-dark-on-accent: '#101c2c'
  orbit-dark-success: '#8ad2b0'
  orbit-dark-success-bg: '#193a34'
  orbit-dark-error: '#ffaaa5'
  orbit-dark-error-bg: '#422e36'
  precision-light-frame: '#f5f6f8'
  precision-light-bg: '#fff'
  precision-light-surface: '#f4f6f9'
  precision-light-text: '#182334'
  precision-light-muted: '#58687d'
  precision-light-line: '#dfe5ed'
  precision-light-control: '#7f8da1'
  precision-light-accent: '#245edb'
  precision-light-accent-soft: '#eaf0ff'
  precision-dark-frame: '#141922'
  precision-dark-bg: '#1b222d'
  precision-dark-surface: '#242e3e'
  precision-dark-text: '#e8edf5'
  precision-dark-muted: '#a9b7cc'
  precision-dark-line: '#3b485d'
  precision-dark-control: '#71839b'
  precision-dark-accent: '#8daeff'
  precision-dark-accent-soft: '#303e5e'
  studio-light-frame: '#e9e6e0'
  studio-light-bg: '#f8f7f3'
  studio-light-surface: '#f0eee8'
  studio-light-text: '#252b34'
  studio-light-muted: '#636970'
  studio-light-line: '#dcd9d1'
  studio-light-control: '#8a8c8e'
  studio-light-accent: '#3159d5'
  studio-light-accent-soft: '#e8ecf9'
  studio-dark-frame: '#181a1f'
  studio-dark-bg: '#22252b'
  studio-dark-surface: '#2c3037'
  studio-dark-text: '#f0efeb'
  studio-dark-muted: '#b5b6b7'
  studio-dark-line: '#42464e'
  studio-dark-control: '#7f858e'
  studio-dark-accent: '#8daeff'
  studio-dark-accent-soft: '#343f5a'
  light-success: '#24734b'
  light-success-bg: '#edf7f1'
  light-warning: '#8a5705'
  light-warning-bg: '#fff7e6'
  light-error: '#bb353d'
  light-error-bg: '#fff0f0'
  dark-success: '#80cea5'
  dark-success-bg: '#20362c'
  dark-warning: '#efc574'
  dark-warning-bg: '#382f20'
  dark-error: '#ff9ba2'
  dark-error-bg: '#3b282c'
  light-on-accent: '#fff'
  dark-on-accent: '#14181e'
  studio-sidebar: '#202936'
  studio-sidebar-text: '#b7c0cd'
  studio-sidebar-active: '#364356'
typography:
  title:
    fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: '26px'
    fontWeight: 650
    lineHeight: 1.35
    letterSpacing: '-0.6px'
  body:
    fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: '14px'
    lineHeight: 1.55
  label:
    fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: '12px'
  metric:
    fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif'
    fontSize: '30px'
    fontWeight: 550
rounded:
  precision-control: '3px'
  control: '6px'
  panel: '8px'
  orbit-panel: '10px'
  precision-panel: '2px'
spacing:
  xs: '4px'
  sm: '8px'
  md: '12px'
  lg: '16px'
  section: '20px'
  panel: '24px'
components:
  button-primary:
    height: '40px'
    rounded: '{rounded.control}'
  button-default:
    height: '40px'
    rounded: '{rounded.control}'
  input:
    height: '40px'
    rounded: '{rounded.control}'
  navigation:
    rounded: '{rounded.control}'
  status:
    rounded: '4px'
    padding: '2px 6px'
  card:
    rounded: '{rounded.panel}'
---

# Design System: LLM Algorithm Harness

## Overview

**Creative North Star: "Frontier · 算法评估工作台"**

本系统记录 Issue #168 已接入的工作台外壳。Frontier SVG 与三套风格均已由用户确认：Orbit 关注运行与恢复，Precision 关注度量与比较，Studio 关注实验记录。三者共享路由、认证和操作语义，视觉切换只改变外观与对应主题偏好。

界面服务于持续评估、检查失败与比较结果。用清晰文字、数字对齐、分组导航和可读状态建立层级；业务与通知明确标注 Mock，账号资料、API 密钥、认证和登出继续使用既有真实实现。

**Key Characteristics:**

- Frontier 前沿切片品牌标记
- 三种风格、六种浅深配色
- 操作界面以任务与数字为中心
- 业务与通知的 Mock 范围明确可见

## Colors

### Primary

每个风格的浅深主色已在 frontmatter 的 `*-accent` 中记录；用于关键操作、链接、选中与焦点。`*-accent-soft` 承载轻量选中和未读底色。AntD token 由 `src/layouts/appearance.ts` 提供，外壳变量与状态色由 `src/layouts/shell.css` 提供；两处源文件共同构成实现权威。此文档是提取快照，修改实现后应同步。Sidecar 的八级 OKLCH tonalRamp 仅为面板合成预览，并非应用新增的颜色阶；预览片段展示语义变量绑定，AntD 完整状态以运行时为准。

### Neutral

`frame` 是外框，`bg` 是内容页，`surface` 是次级表面；`text` 与 `muted` 分别承载正文和辅助信息。`line` 仅作结构分隔，交互边界使用 `control`。Studio 侧栏在两种主题中均使用石墨底及独立浅色文字。

### Semantic states

浅深共享成功、警告、错误 token；Orbit 深色覆盖成功与错误 token。其余模式继承相应主题的共享状态值。主要按钮前景使用 `on-accent`；Orbit 深色单独覆盖。Studio 页标题区的主要操作使用正文色底、内容页色前景。

**The Semantic Pair Rule.** 每次调整配色都检查前景与背景这一对；分隔线不能替代可操作控件边界。

## Typography

字体与字号来自现有操作界面。正文使用 frontmatter 的系统字体栈，数字采用 `tabular-nums`，不加载外部字体。标题基础样式为 `title`；手机标题为 24px，Studio 桌面为 28px、手机为 25px。区块标题 16px/600，辅助信息 12px，关键指标通常 30px/550，手机 28px；各风格首屏的比较值另有局部排版。

这些是操作界面的层级，不是为营销大标题建立的展示字体规范。代码与日志后续页面需要按实际内容另定等宽字体。

## Layout

桌面由常驻侧栏与内容页组成。完整侧栏宽度分别为 Orbit 220px、Precision 208px、Studio 240px；1024–1279px 统一为 200px，折叠为 76px。顶栏通常为 64px；手机为 60px（Studio 顶栏保留其 64px 覆盖）。主要间距提取在 frontmatter，内容留白与列宽随风格和视口变化。

- 320px 是本轮最小验收宽度；小于 360px 有额外顶栏与首屏紧凑规则，不代表支持无限缩窄。
- 768px 以下为单列，常驻侧栏隐藏，抽屉提供完整导航；底部固定仪表盘、题目库、评估、结果四个入口。任务行转换为带字段标签的卡片式布局，内容页预留 100px 底部空间，并考虑 safe area。
- 768–1023px 隐藏常驻侧栏、使用导航抽屉，无底部导航；主任务区全宽，辅助信息按可用空间排列。
- 1024–1279px 使用常驻可折叠侧栏；主任务区全宽，辅助区移到下方。Orbit 执行焦点与 Precision 对照区域同时收紧。
- 1280px 起采用完整风格侧栏和主辅列；这由前一段媒体查询结束产生，不是额外的 `min-width:1280px` 规则。
- 1440px 是桌面验收视口；CSS 没有独立 1440px 断点。1536px 起实际样式进一步加大内容留白与部分辅助列宽。

**The Stable Shell Rule.** 风格切换不得改变当前路由或通过重新挂载清空仍挂载页面的交互状态；跨路由是否保留业务状态由业务页生命周期决定。

## Elevation & Depth

静止的内容面板通过背景层级和细边界分隔，无额外自定义投影。浮动菜单、Drawer、Modal 的层级与阴影沿用 AntD。外观切换仅对背景、文字和边界颜色作 180ms ease 过渡，不对布局作补间；控件有 150ms 状态过渡，品牌有 160ms 位移反馈。`prefers-reduced-motion: reduce` 通过响应式订阅把 AntD `token.motion` 设为 `false`，避免浮层在动画初始缩放态定位；其余自定义动画时长缩短为 0.01ms、关闭过渡、动画迭代次数设为 1，并关闭顺滑滚动，以保留 AntD 浮层关闭所需的结束事件；自有 DesignFocus 动画仍直接禁用。

## Shapes

基础控件圆角为 6px，Precision 为 3px；面板基础为 8px，Orbit 为 10px，Precision 为 2px，Studio 最近任务与辅助容器采用直角与规则线。手机内容页缩小圆角，Modal 覆盖为全屏直角。形状属于风格语法，不把某个风格的直角推广为另外两套的约束。

## Components

### Buttons and fields

AntD 提供按钮、输入、Select 和表单状态，主题映射控制基础 40px 高度。手机主要按钮、输入与关闭操作按 CSS 扩展到 44px。可聚焦按钮和链接显示主色 2px 焦点轮廓；选择器保持明确标签。六套模式中的输入占位文字均使用 `colorTextSecondary` 映射为 `colorTextPlaceholder`，保持与辅助文字一致。具体状态由 AntD 运行时算法和外壳 CSS 共同决定。

### Navigation

`src/routes.tsx` 是路径、标签、分组、图标和 `allowedRoles` 的共同来源。侧栏和抽屉复用 Navigation；窄屏 MobileNav 仅选择四个常用入口。折叠后保留可访问名称与 Tooltip。面包屑由当前路径生成，设置子页额外提供返回设置入口。导航后 main 获得焦点；页面有“跳至主内容”链接。手机风格与主题选择区另显示“业务与通知 · Mock”，使收起桌面标记后仍能识别示例范围。

### Notifications

通知用 Badge 与 Drawer，桌面宽 420px、手机全宽；支持分类、单条已读、全部已读、清空和站内跳转。通知状态属于当前登录会话 marker 对应的内存 store；换 marker 重新创建，刷新恢复种子数据。它不写入 localStorage，不跨设备同步。

### Feedback and task content

`src/components/common/Feedback.tsx` 提供 Loading、EmptyState、ErrorState、真实 React ErrorBoundary 和四类可关闭 Toast 示例。加载有 `aria-busy` 与状态文字，错误有 `role=alert`。业务页的状态选择器用于 Mock 演示；模拟超时重试不是网络重试。ErrorBoundary 以路径为 key 在导航后重置，重试按钮重新尝试渲染。

任务列表、指标、创建表单、导入与恢复均在 `src/mock/`。运行状态同时显示符号和文字；未完成任务无最终 Pass@1。Frontier 主资产为 `public/brand/harness-frontier.svg`，单色版本为 `harness-frontier-mono.svg`，均为透明 SVG；侧栏与手机品牌复用主资产。应用名来自现有环境配置；默认完整名称 `LLM Algorithm Harness` 在侧栏与手机使用 `Harness` 紧凑字标，完整名称仍保留在 title 与可访问名称中；其他配置名称直接显示其原值。

## Do's and Don'ts

### Do:

- **Do** 从 appearance.ts 与 shell.css 提取或修改语义 token，并保持 AntD 与外壳配色一致。
- **Do** 在浅色、深色和窄屏上检查同一操作的完整状态。
- **Do** 保留真实认证与角色守卫，业务示例持续标明 Mock。
- **Do** 对运行、完成、失败同时展示文字与符号。

### Don't:

- **Don't** 用视觉风格作为 React key 重新挂载外壳或业务页。
- **Don't** 在界面加入 Mock 角色切换或把本地通知描述成服务端消息。
- **Don't** 用未完成任务的部分通过率冒充最终结果。
- **Don't** 将历史独立原型入口或临时目录当作仓库交付文件。
