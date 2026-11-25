# #474 Web 相似题审核与合并验证

## 结论与范围

本次实现覆盖已批准 change `review-similar-problems` 的 6 项要求、14 个场景及 8 项任务。扫描、逐组选择、独立版本保存、权限、过期、幂等和引用兼容的相关检查通过。完整仓库测试未完成，不能据本报告宣称全仓测试或覆盖率达标。

沿用已确认的 direct / direct / off 配置，未执行独立 reviewer 审查。本文记录实现者核查与自动化验证，不将其称为独立验收。未调用模型供应商或启动真实 Eval。

实际交付文件为 18 个：实现 10、测试 5、文案 2、用户文档 1（不含 Comet 产物和本报告）。相比最初 10–14 个估计，增加的文件用于独立组件、浏览器回归以及项目要求的 OpenAPI 和路由契约；功能、验收及风险边界仍为用户批准的 #474。继续 tweak 的决定已绑定本 Run 的范围复核提案。

## 规格与设计核查

| 要求 | 实现证据 | 验证证据 |
| --- | --- | --- |
| 个人题库相似题只读预览 | `api/files/deduplication.py:preview_deduplication`；复用共享来源指纹与 TF-IDF 函数，保持 CLI 不重叠分组顺序，返回实际得分与合并方案 | `tests/test_web_deduplication.py`：只读快照、文本阈值、空库、空词表；`tests/test_deduplication.py`：严格阈值及指纹低分展示 |
| 只保存批准的相似题合并 | `save_deduplication` 校验组及保留题，以完整源库副本应用选定组 | 非推荐保留题、完整正文/列表/元数据、跳过组、未知组、重复组、组外 ID 和零选择回归 |
| 合并确认的修订与幂等边界 | 所有者和修订绑定令牌；FileStore 写事务中核验修订并原子插入版本/唯一确认回执 | 并发四次确认只产生一版；重启后及源库后续更新后重试返回原版；提交时竞争更新拒绝；账号隔离；清理版本后重试 410 |
| 合并版本兼容已有引用 | 保存完整独立版本，复用版本读取和评估冻结流程；保留源库 | 新版本创建评估并读取冻结正文、标签；原版本、推荐题集及历史结果保持可读 |
| 批量治理中审核相似题 | `DeduplicationReview.tsx`、治理抽屉页签、双语文案、保留题选项及完整字段预览 | 浏览器覆盖扫描、保留题切换、跳过组、无候选、错误重试、字段变化、保存导航；桌面和 390px 截图 |
| 相似题审核保存的状态隔离 | 请求取消、参数变化清理审核、同步提交锁及当前账号身份检查 | 浏览器覆盖过期清理、阈值变化、迟到扫描、重复点击和账号切换；API 覆盖重复确认 |

设计一致性：使用现有个人库、治理、认证、SQLite 写事务及版本评估入口，没有新增外部依赖。列表字段及主版本完整度推荐调用 CLI 同一函数。相似度按同一全库词权重分块计算，避免分配完整稠密方阵。前端只提交批准组，不回传任意合并载荷；服务端重算验证内容。

## 已通过检查

工作目录均为仓库根，前端命令在 `frontend/` 执行。

- `.venv/bin/pytest tests/test_web_deduplication.py tests/test_deduplication.py tests/unit/test_api_endpoints.py -q --no-cov --disable-warnings`：987 passed。日志 `/private/tmp/issue-474-final-targeted.log`。
- `.venv/bin/pytest tests/test_api_evaluation_options.py tests/test_dataset_references.py -q --no-cov --disable-warnings`：91 passed。日志 `/private/tmp/issue-474-legacy-final.log`。
- `.venv/bin/pytest tests/test_api_documentation.py -q --no-cov --disable-warnings`：25 passed。日志 `/private/tmp/issue-474-doc-final.log`。
- `npm test`：367 passed。日志 `/private/tmp/issue-474-frontend-final.log`。
- `npm run lint`、`npm run format:check`、`npm run build`：通过，构建包含 TypeScript 检查。构建保留已有的较大 chunk 提示。日志 `/private/tmp/issue-474-lint-final.log`、`/private/tmp/issue-474-format.log`、`/private/tmp/issue-474-build-final.log`。
- `.venv/bin/ruff check` 和 `ruff format --check` 覆盖变更 Python 文件：通过；`git diff --check`：通过。
- `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/verify-deduplication.mjs`：通过。该测试使用真实页面和 API fixture，后端持久化及评估创建由上述 pytest 集成测试覆盖。日志 `/private/tmp/issue-474-browser-final.log`，截图 `/private/tmp/issue-474-review.png`、`/private/tmp/issue-474-mobile.png`、`/private/tmp/issue-474-versions.png`。
- `comet classic openspec -- validate review-similar-problems --strict`：通过。
- 10,000 题阈值 1 的扫描测量：返回零文本候选，耗时约 1.13 秒，进程峰值约 170.5 MiB；该测量不代表大重复组响应的压力验证。

## 全仓检查与修复回执

执行过裸 `.venv/bin/pytest`。受限环境中发现以下问题后主动中断，退出码 2；中断前为 632 passed、5 skipped、2 failed、4 errors，未完成全量及覆盖率检查。日志 `/private/tmp/issue-474-full-pytest.log`。

- `test_every_http_operation_has_actionable_documentation` 与 `test_all_json_examples_validate_against_route_models`：新端点缺少 OpenAPI 注册及请求示例。已补齐 `api/documentation.py`，完整文档测试 25 项复验通过。
- `TestPricing.test_full_model_ids_round_trip_over_http`、`TestPricing.test_full_model_id_auth_and_validation_over_http`、`test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]` 与 `[ab]`：均在 `pricing_http` fixture 的本机 `listener.bind` 处出现 `PermissionError`。允许临时本机测试服务器后，用同样四项测试复验为 4 passed。日志 `/private/tmp/issue-474-port-tests.log`。
- 早期仅运行 15 项的 pytest 命令因项目默认全仓 90% 覆盖率阈值退出 1，当时用例均通过；相关回归最终显式使用 `--no-cov`。本报告不以局部运行声称全仓覆盖率达标。

## 限制与交付状态

源库与历史引用保持不变，新版本遵循既有每用户最近 50 版保留策略，已清理结果的确认回执返回 410，避免重建旧确认。大重复组的响应体仍随匹配对及保留选项增长，未执行全库均重复的压力测试。

未部署、未提交 Git、未推送、未创建 PR；等待 Archive 阶段的当前交付决定。Issue 范围未发现未解决的 CRITICAL 或 IMPORTANT 问题。
