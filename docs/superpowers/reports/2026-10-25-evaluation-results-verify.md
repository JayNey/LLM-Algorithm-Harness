# #226 真实结果列表与详情验证报告

日期：2026-10-25（Asia/Shanghai）。分支 `tweak/20261025/evaluation-results`，change `evaluation-results`，base=main。基线 `7d88dc023924b8944a821026e6270e0d7b11f03f`；最终受测源码 `cd4abd75ad1522779a5591b6bd6fb287bb4812bc`。用户沿用增量Tweak、个人任务分支、独立Bugbot审查及修复后交付PR的流程。

## 前置与实现范围

#220/#224/#225已关闭，其客户端、详情动作及进度观察代码已合入main；#259权限清理/重试恢复补丁也已合并，源码已核对，相关PR及基线main均10项CI成功。首次实际results验收确认原ResultsPage仍导出Mock BusinessPage，因此按#226实现，不重复已合入的前置。

- `/results`使用共享认证客户端results接口和useList，状态/limit/offset保存在URL，筛选清零、越界页恢复、加载/空/失败重试分别呈现。链接使用返回id作为evaluation ID，run_id为空仍可进入详情。
- `/results/:evaluationId`可直接访问/刷新/恢复单题分页。任务事实来自get，策略汇总和单题页来自result。result.strategies直接渲染，不按当前problems.items重算。
- 同题不同策略用JSON编码的[problem_id,strategy]作为键；状态保留原值，null显示未知，零仍是零，耗时用秒、成功率乘100。费用有unknown_cost_count时明确已知估算和未知条数，不把未知写成免费。无代码、输出或单题错误的虚构字段。
- 联合loader使用同一signal并发读任务和结果，等待两者完成后才结束观察周期。普通结果失败保留成功任务及独立resultError；任务失败不发布同时读取的结果；结果401/429交还既有观察器恢复/退避。换页、账号、客户端、loader身份及AbortSignal共同拒绝旧数据。
- React读取适配器支持稳定的联合loader和可选result/resultError快照字段，观察器核心及其时序规则未修改。活动详情手动刷新复用同一观察器；终态/paused停止，WS4403清除后显式重试恢复。

## RED、调查与审查修复

1. results fixture在原Mock页面等待真实结果表格5秒超时，退出1。确认页面未接入真实列表，而非接受Mock数据作为成功。
2. 首轮fixture已有12组静态/分页/失败断言通过；Ant Design将两个汉字的按钮名插入空格，重试定位改为既有脚本使用的`/^重\s*试$/`。随后联合周期因初始结果请求比任务请求慢而混入事件后的计数；等待两路初始读取均结束再发三条事件，严格保留“事件后一次任务+一次结果”的断言，未放宽为允许重复刷新。
3. 独立Bugbot发现1项P2：并发读取可能跨终态提交，任务completed但结果仍running，观察器会过早停止。新增两个单测先失败；联合loader现在在同一周期内有序补读结果一次。仍不一致时清除旧结果、显示独立错误/显式重试，不改写任务状态、不无限重读。修复后37项loader/observer/presentation重点测试通过。
4. 最终Bugbot复审无剩余问题，审查者独立运行73项评估测试全部通过，未修改源码。审查覆盖修复在内的整个分支；其结果作为最终集成审查证据复用。

## 实际验证

以下GREEN命令退出0，RED步骤除外：

- frontend `npm test`：229 passed、0 failed。新增联合读取/部分失败/401与429传播/取消隔离/终态对账，以及结果状态与未知成本表现测试。
- `npm run lint`：0错误、2条未改动BenchmarkDetailPage.tsx既有runFinished依赖警告。`npm run format:check`通过。
- 初版`npm run build`类型/生产构建通过，保留既有chunk大于500kB提示；最终正式Runtime构建在交付段补记，不用初版结果代替最终构建。
- 最终浏览器all107组通过，包含results18组（其中全局未知请求检查共享），源码/fixture在开始时均干净；静态fixture的任务计数/策略/模型已校正为与结果记录一致。人工已检查[390px截图](../../frontend/assets/evaluations/results/results-390.png)和[1440px截图](../../frontend/assets/evaluations/results/results-1440.png)，表格可独立横向滚动，根页面不溢出；不把这两个Orbit/dark样例外推为完整外观矩阵。
- OpenSpec strict、git diff --check通过。

[公开JSON](../../frontend/assets/evaluations/results/all.json) 保存实际git HEAD/dirty、替换依赖、全部断言/请求/截图，以及results_evidence：初始两路请求结束后，三条WS事件合并成一个联合周期，两路HTTP并行、周期不重叠。HTTP任务显示60%，结果平均Token显示300，未直接应用WS中的50%载荷。

## 规格核对

完整性：5/5任务、3/3项requirement、8/8场景已核对；无剩余实现/审查问题。最终正式验证与交付状态在下文记录。

- 当前用户列表：状态筛选/URL/翻页/刷新、run_id=null详情由results浏览器覆盖；身份/查询异步隔离复用useList及其实际React生命周期回归。
- 全量策略汇总与单题分页：跨页汇总不变、同题多策略、秒/百分率、null与零、未知成本与未知状态由浏览器及presentation单测覆盖。服务端汇总不在前端重算。
- 联合快照：浏览器三事件单周期、并行双接口、503任务保留、HTTP403清理、WS4403重试恢复、迟到分页后退隔离；loader单测验证忽略AbortSignal也不交付、失败不伪装空结果、401/429传播和终态有界对账。既有observer假时钟测试覆盖合并、降级、退避、权限、dispose及操作纪元。
- 实现与change/design.md一致，无新增后端接口/数据库或依赖。未另建技术Design Doc，该额外文档检查不适用。Tweak文件提示阈值按用户既定的自包含前端接线流程处理；采用full验证覆盖新增delta，不升级或重做架构。

## 验证层级与复现

在frontend先`npm ci`并启动`npm run dev -- --host 127.0.0.1 --port 5180`。另终端设置`PLAYWRIGHT_MODULE=/absolute/path/to/playwright`后执行`node scripts/verify-evaluations.mjs --scenario results`或`all`。`EVALUATION_BASE_URL`覆盖地址，`EVALUATION_QA_DIR`覆盖产物目录，`CHROME_PATH`可选，否则使用Playwright Chromium。

fixture使用真实React StrictMode、路由、session provider、创建store、评估HTTP客户端和ProgressObserver；替换身份/业务HTTP及WebSocket，不连接上游WS。未运行真实API登录、Redis/Celery、供应商、沙箱、Safari/Firefox或真机。没有新增后端测试，不能将前端fixture或平台后端CI当作真实端到端证明。

#227继续负责失败/部分/无结果的细化语义，#228负责统一入口和外壳Mock标记，#229负责完整风格/主题/宽度矩阵，#231/#232负责质量与真实联调。当前仍保留外壳的既有Mock标记，结果页本身从现有API读取。

## 交付与正式Runtime记录

[PR #267](https://github.com/JayNey/LLM-Algorithm-Harness/pull/267) 已创建，base=main，Refs #226。最终正式build/verify守卫及平台CI状态将在此补记。未自动合并、关闭issue或归档；作者提交排除.comet/.claude/.codex/.agents/skills-lock.json。
