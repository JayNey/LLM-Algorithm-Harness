# 部署种子题库 worker 兼容性验证

结论：PASS。change：fix-deployment-example-problems；分支：hotfix/20261023/fix-deployment-example-problems；实现提交：efd3a00。

## 验证范围
- 任务完成：3/3，覆盖复现、数据修复、回归和根因检查。
- 改动一致：3 个实施文件，其他为本 change 的流程元数据。自动 scale 因含元数据计数 15 判为 full；按实际仅三文件数据修复、3 任务、无 delta 手动选择 light。
- 编译通过：`python3 -m compileall -q scripts/seed_data.py tests/test_seed_data.py`，退出码 0。
- 相关测试通过：`python3 -m pytest tests/test_seed_data.py tests/test_deployment_config.py tests/test_problem_loader.py tests/test_sandbox_executor.py -q --no-cov -o addopts=`，98 passed；验证阶段独立复跑通过。
- 安全检查通过：只修正可信示例数据，未新增凭证、网络或 unsafe 操作；测试只在临时 SQLite 和 host 沙箱执行固定参考解。
- 自动集成审查：按 hotfix 的 review_mode=off 跳过。人工核对 diff 未见正确性或边界问题。

## RED / GREEN
旧版新增参数化回归 3 failed / 2 passed，三道题均因缺 expected_output 在 worker _to_domain_problem 失败。修复后首次 seed 和旧行重播均执行通过全部六个公开用例。参数字典及列表、布尔、整数输出均由真实沙箱验证。

## 其他检查与限制
- Ruff、Black 检查、git diff --check、OpenSpec validate 通过；无 API 或 schema 改动。
- 测试保留 4 项既有警告：Pydantic class Config 弃用、TestCase 收集、class-scoped fixture 弃用（两次）。
- 未运行全量测试或生产部署；未验证远程模型生成；数据兼容性由真实 worker adapter 与 host 沙箱覆盖，既有 Docker 部署测试通过。
- 已部署旧记录需更新代码并对原业务数据库重新运行 scripts/seed_data.py；未修改任何实际部署数据库。
- comet task 上下文插件因 ~/.comet/plugins/state.json.lock 的 EPERM 不可用，按技能协议不阻断修复。
