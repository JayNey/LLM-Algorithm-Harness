# #322 基准运行历史与刷新恢复验证

基线 main@8a6ab918c3f70e38e9c00d4251f9d4343da98120；独立分支 feat/322-benchmark-run-history。已确认的设计与 delta spec 位于 openspec/changes/benchmark-run-history，执行采用 autonomous / tdd / standard。

## 行为与实现

历史采用真实服务端状态过滤、分页及总数；URL 的 run_id 直接加载详情，当前列表页不限制显式选择。仅全部活动查询成功且总数确为一条时自动恢复，多条时提供选择。运行/任务关联核对套件、实体和任务类型；终态刷新资源一次并停止轮询，暂停/错误可手动重新核对。旧请求、账号或套件切换及迟到的提交响应均隔离。曲线点击和键盘链接使用同一 run_id，原模型/策略、个人数据集与套件编辑保留。

## TDD 与修复证据

- 客户端 RED：新增 runs 尚不存在，详情/曲线丢弃关联标识；URL 策略文件尚未实现。GREEN：合同和 URL/关联测试 11/11。日志 /tmp/322-red-contract.log、/tmp/322-green-contract.log。
- 页面 RED：运行历史标题不存在。任务关联错误 RED：错误未显示且继续重试。实现后浏览器通过。日志 /tmp/322-red-page.log、/tmp/322-red-association.log。
- 分段独立审查发现三项 P2，均有实际 RED：暂停后重试出现陈旧中断警告（1 != 0）；paused 运行遮蔽关联错误；POST 等待期间翻页，返回后 offset 从20退回空。日志 /tmp/322-red-resume.log、/tmp/322-red-masked.log、/tmp/322-red-launch-url.log。早先的脚本路径/选择器错误未计为行为 RED。
- 修复为成功 tick 清 paused、优先显示实际错误、按最新已提交 URL 写入新 run_id。相同独立审查者定点复审通过，未发现新增缺陷。

## 实际验证

- 前端全量测试：308 passed、0 failed。
- ESLint：0 errors、0 warnings；TypeScript/生产构建通过，保留现有大 chunk 提醒。
- `frontend/scripts/verify-benchmark-history.mjs`：18 项浏览器 fixture 检查通过，无页面异常/未知请求；包含刷新、分页外运行、失效/跨套件链接、多活动选择、暂停与终态停止、暂停后重试、错误关联、提交期间分页、慢响应隔离、曲线导航、中英文和320px。
- 既有 `verify-benchmarks.mjs all`：5项通过、unknown=0；`verify-dataset-references.mjs`：5场景通过，三类业务仍按真实契约提交个人数据集。
- `scripts/verify_benchmark_history.py`：隔离真实 TCP API+SQLite+Cookie 认证+浏览器联调9项通过，无页面异常。明确播种27条 BenchmarkRun 和2条 AsyncTask状态，未调用模型/Worker，不将播种状态称为真实基准执行。
- 两份可复跑脚本均随代码提交；真实 HTTP 脚本自动启动/停止临时 API/UI，环境及账号不复用生产数据。PLAYWRIGHT_MODULE 和 CHROME_PATH 可指向本机安装。
- 未修改后端历史服务，无数据库变更；独立 PR 不依赖 #319。

## 流程状态

当前记录覆盖 Build 实现与分段审查。Verify 最终集成审查、Comet守卫及PR/CI结果将在实际完成后补记，不以本报告代替守卫或最终审查。
