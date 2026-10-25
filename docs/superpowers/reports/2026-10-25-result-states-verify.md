# Issue #227 结果状态语义验证

Change：`distinguish-result-states`。基线：`be54ba8ed44bf199e53a0a98aec3fee9294075a3`，来自最新 origin/main；前置 #224、#225、#226 已关闭，复用 main 中的真实客户端和页面。用户已选择继续 tweak，接受文件数超过提示阈值。

## 改动与验收映射

- `presentation.ts`、`types.ts`：pending/running 零记录 waiting、有记录 partial；paused/failed/cancelled 保留对应类型和记录数；completed 零记录 empty、少于预期 incomplete、达到预期 complete；跨版本和未知状态 unknown。使用 problems.total，而非当前页条数。
- `ResultDetailPage.tsx`：分别显示任务详情原因、可用性、已记录/预期数和独立结果读取错误；明确部分结果不是最终统计。沿用 Frontier/Orbit/Precision/Studio、主题、移动导航和原有表格。
- `results.ts`：task 或 result 的 403/404 优先清除整项资源，即使另一端503；result503 保留任务事实并返回 resultError。沿用既有单次终态补读；仍不一致显示未确认和手动重试，不无限轮询。
- `useEvaluation.ts`：live 权限拒绝同时使 bootstrap 缓存失效并递增读取纪元，防止迟到响应或随后503恢复旧数据。
- presentation/results/observer 测试与 states fixture 对应 delta spec 的三组场景；无新 API、数据库变更、认证客户端或 Socket.IO。

## RED / GREEN

1. 新 presentation 矩阵在旧实现上得到 empty 而不是 waiting；result403/404 与补读403未抛出，3项失败（公开附件 `assets/result-states/unit-red.txt`）。
2. observer 联合结果403发布了task快照而未发forbidden，新增回归失败（公开附件 `assets/result-states/observer-red.txt`）。
3. states fixture 在实现前等待“等待结果”超时（公开附件 `assets/result-states/states-red.json`）。
4. 追加task503/result403用例，旧实现抛出503，回归失败；修复为任一权限拒绝优先后通过（公开附件 `assets/result-states/denial-red.txt`、`assets/result-states/denial-green.txt`）。
5. 浏览器首次计数包含StrictMode废弃挂载请求；改为稳定完成页面上显式刷新一个周期，再断言task1/result2，避免把废弃请求误当补读。生产补读次数由单测和浏览器共同验证。

## 命令与层级

以下命令在 frontend 运行，退出码均为0：

- `npm test`：255项通过，无失败。
- `npm run build`：TypeScript/Vite通过；保留既有大chunk提示。
- `npm run lint`：0错误，BenchmarkDetailPage已有2条exhaustive-deps警告，本次未修改该文件。
- 对本次9个源码/测试/fixture文件运行 `prettier --check`：通过。
- `node scripts/verify-evaluations.mjs --scenario states`：21项通过。
- `node scripts/verify-evaluations.mjs --scenario results`：18项通过。
- `node scripts/verify-evaluations.mjs --scenario progress`：7项通过。
- 根目录 `comet classic openspec -- validate distinguish-result-states --strict`：通过。
- 根目录 `git diff --check`：通过。

浏览器使用本机Google Chrome headless、现有外部Playwright模块和Vite开发服务。复现时配置 `PLAYWRIGHT_MODULE`、`CHROME_PATH`，可选 `EVALUATION_QA_DIR`；脚本默认连接 http://127.0.0.1:5180。运行 `npm run dev -- --host 127.0.0.1 --port 5180` 启动页面。

## 场景覆盖

- 13组状态×零/部分/完整记录矩阵；任务原因只来自详情。
- 活动页面已有bootstrap/live数据时，task403/result200、task200/result403及WS4403清除模型与结果；随后task503不恢复旧缓存，授权成功才恢复。
- task200/result503为独立错误，不显示empty或旧统计；显式重试恢复。
- 终态running→completed单次补读收敛；持续running仅补读一次，显示未确认并能手动重试。
- 三风格×浅深主题×320/1440px，共12张截图，均无根页面水平溢出。已人工查看Orbit深色窄屏和Studio浅色桌面截图；沿用现有横向表格滚动。

证据目录：`assets/result-states/`，包括states/results/progress JSON和12张状态截图。JSON保留源代码HEAD、是否dirty、HTTP请求与断言；测试数据和HTTP/WS均明确为fixture。

## 验证边界

已验证：纯TypeScript客户端/表现/观察器单测，真实React/router/session/client的浏览器fixture、Chrome合成视口。HTTP和WebSocket均由fixture替换。

未验证：离线真实HTTP后端、真实Redis/Celery、供应商、沙箱联调；真实移动设备、Safari/Firefox和屏幕阅读器。不得将本报告作为后端E2E或全流程质量验收，后续由 #231/#232/#233 汇总。

## 完整性与一致性

单一ADDED requirement的3个scenario均有实现与测试；design.md与实现一致，无spec漂移。Tweak不要求独立Superpowers Design Doc/完整plan，采用本change精简design.md。无未实现的范围缩减。

## 独立代码审查

独立reviewer对比基线be54ba8审查完整diff，未发现Critical/Important问题；独立运行presentation/results/observer定向套件43项通过。审查覆盖权限优先级、bootstrap/live双缓存与迟到响应、终态补读上限、错误独立性和spec契约。真实后端/供应商/沙箱与独立视觉评估不属于其已执行验证；截图已由实施者查看。
