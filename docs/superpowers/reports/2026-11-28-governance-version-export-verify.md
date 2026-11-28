# Issue #529 验证报告

## 结论

已实现并核对全部 5 项任务、3 条新增要求及 10 个验收场景。实际修改 12 个交付文件，符合用户批准的单 change 范围。采用 Runtime 当前 `direct/direct/off` 配置，未运行独立 reviewer；不将实现者自查称为独立审查。

## 实际检查

| 检查 | 结果与证据 |
| --- | --- |
| 相关后端回归 | `.venv/bin/pytest tests/test_governance_version_export.py tests/test_web_deduplication.py tests/test_api_evaluation_options.py tests/test_api_files.py -o addopts='' -q`：177 passed，见 `/private/tmp/issue-529-pytest.log` |
| 补齐部分批准与去重导出场景后 | `.venv/bin/pytest tests/test_governance_version_export.py -o addopts='' -q`：7 passed（其中原有 5 项包含在上一行），见 `/private/tmp/issue-529-export-tests.log` |
| 前端测试 | `cd frontend && npm test`：386 passed，见 `/private/tmp/issue-529-frontend-tests.log` |
| 浏览器 mock 验收 | `cd frontend && CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node scripts/verify-governance-export.mjs`：退出 0；真实下载 Blob 字节、选择参数、错误与重试、重复点击、版本与账号切换隔离、版本创建评估链接均通过 |
| 前端生产构建 | `cd frontend && npm run build`：退出 0，含 TypeScript 检查；见 `/private/tmp/issue-529-build.log` |
| 格式与静态检查 | 本次 5 个 Python 文件的 Ruff 与 Black；7 个前端文件的 ESLint 与 Prettier；`git diff --check` 均通过 |
| OpenSpec | `comet classic openspec -- validate governance-version-export --strict` 通过 |
| 新增后端实现类型检查 | `mypy --follow-imports=silent --disable-error-code=import-untyped api/files/store.py api/files/governance.py api/files/service.py`：3 个文件通过 |
| mypy 回归对比 | 对当前代码和 HEAD 的同一组 5 个后端文件运行 mypy，原始检查均退出 1、均为 13 项既有错误；忽略行号后错误内容完全一致，对比断言通过。见 `/private/tmp/issue-529-mypy-current-comparison.log` 与 `/private/tmp/issue-529-mypy-baseline-comparison.log` |

完整 mypy 的既有错误包括缺失第三方 stubs、既有推荐空状态类型和其他路由类型问题，不把原始 mypy 失败记作通过。未为此 change 修改无关代码。构建包含现有大 chunk 提示；pytest 包含既有弃用提示。首次浏览器启动缺少 Playwright 浏览器，改用已安装 Chrome；Vite 缓存过期导致的模块 504 通过强制重建开发缓存消除。下载错误场景中的 409/404/503 和切换时的取消请求是预期测试输入。

## 完整性与正确性

| 规格场景 | 实现与验收证据 |
| --- | --- |
| 完整快照可重新导入 | `FileService.export_dataset_version` 读取保存快照；专题测试核对全部 Problem 字段、Bob 实际重新导入，以及 Alice 版本评估和 Bob 导入后评估的冻结内容 |
| 去重版本复用完整下载 | 专题测试实际扫描、批准去重并保存，然后核对完整导出与 merged_from、测试、判题、来源元数据 |
| 用户隔离与版本清理 | 下载端点使用 Cookie/Bearer 身份；按 user_id + version_id 查询；专题测试覆盖他人、不存在、清理后、未登录，报告随快照外键级联删除 |
| 主库导出不受影响 | 专题测试比较个人主库导出仍为原始主库；现有文件处理测试通过 |
| 报告描述实际批准 | 专题测试对比原标签/新标签、原难度/新难度及 approval；无实际变化的批准不生成报告项；单独批准难度时标签和未批准题目不变 |
| 历史报告不漂移 | 保存后改变主库并删除评估记录，重新实例化 FileStore 后的报告与下载字节保持一致 |
| 无历史依据明确说明 | 旧库模拟升级及去重版本报告返回 409，仍能导出完整数据；浏览器呈现明确中文错误并允许重试 |
| 切换版本后下载对应选择 | 浏览器核对 A/B 请求路径及实际下载字节；详情加载时无旧下载按钮；旧下载延迟响应被取消 |
| 下载失败可见 | 浏览器覆盖报告缺失、版本清理和服务失败，错误响应不保存为文件，恢复后下载成功 |
| 账号切换隔离 | 浏览器在下载期间实际切换会话，旧响应不产生下载；共享客户端保留会话刷新和凭据，客户端测试验证取消信号 |

## 设计一致性

- 完整导出直接读取数据库快照，不使用详情摘要，也不读取主库补全。
- 报告与版本同一事务保存；报告写入失败时版本回滚，过期 source_revision 不保存；清理保持原版本保留策略。
- 独立报告表兼容已有版本表；缺失报告明确反馈，不生成猜测差异。
- 前端沿用共享 HTTP 客户端，按版本挂载下载组件并在卸载时取消。按钮具有稳定可访问名称与下载期间互斥。
- 不调用付费模型，不部署、不推送、不关闭 Issue。代码与归档交付等待最终授权。

未发现本次范围内的 CRITICAL 或 IMPORTANT 问题。独立审查按 Runtime 的 review_mode=off 不适用；已有完整 mypy 失败已逐项与 HEAD 比较，未新增诊断。
