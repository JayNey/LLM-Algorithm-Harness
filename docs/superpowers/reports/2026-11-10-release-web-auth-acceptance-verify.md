# #444 发布候选会话与权限正式验证

2026-11-10。变更 `release-web-auth-acceptance` 在分支 `tweak/20261110/release-web-auth-acceptance` 完成完整验证，结论为 **PASS**。实际浏览器、API 和镜像结果见 [发布候选验收记录](../../../openspec/changes/archive/2026-11-10-release-web-auth-acceptance/evidence.md)。

## 完整性

- 四项任务全部完成。使用同一隔离生产 Compose 的两个普通账号和一个管理员，复核会话、角色、私有资源和密钥。
- OpenSpec 严格校验通过。原生 delta 输出识别 `api/cost-management` 和 `frontend/pricing-management` 的两项修改要求，分别包含六个和四个场景。按原生输出逐项核对。

## 正确性

- **会话与账号切换**。真实签发的 60 秒令牌到期后返回 401，浏览器刷新访问 Cookie、刷新 Cookie 和 CSRF。旧 CSRF 返回 403，新 CSRF 可写。错密、回跳、浏览器重开、改密与登出重放均有证据。同一文档切换账号后，延迟的旧请求在浏览器标记为失败，页面只显示新账号数据。
- **资源隔离与管理入口**。普通用户的管理深链接显示权限提示，对应状态、日志和沙箱诊断 API 返回 403。管理员可调用这些入口。普通账号的私有资源读取与修改按各端点契约返回 404，属主列表和读回作为对照。
- **定价与脚本兼容性**。登录用户可查询共享目录与历史，普通用户不能写，管理员可追加含斜杠模型与零价版本。回归覆盖版本顺序、模型 ID 编码、无效值和已知零成本。普通验收账号对目录仅执行 GET，单价不匹配时在评估提交或改变重试状态前停止，管理员准备匹配价格后预检通过。
- **公开契约**。已同步 API 与前端要求、OpenAPI、帮助页和运行手册。API v1 保留原路径并收紧写权限。原普通客户端的写入现返回 403，追加由部署者配置的管理员执行。Cookie 写入须带匹配的 CSRF 头。

## 一致性与审查

实现复用可信管理员依赖与前端角色上下文。独立审查发现的脚本权限冲突、公开契约漂移、帮助文案和在途证据问题均已修订并复核。用户确认在 tweak 中继续修订。

普通用户与管理员的预检在重建后的生产 Nginx 与 API 镜像通过。最终补充的 CSRF 说明在生成的 OpenAPI 中核对。1086 项后端回归通过，其中包含 API v1 契约测试。最终 OpenAPI 文案修改后单独复跑 23 项契约测试，全部通过。344 项前端测试、生产构建、live 脚本自测、Black、Ruff、Prettier 和 Git 空白检查通过。Vite 提示既有大分包，Python 测试提示既有依赖弃用。

```sh
python3 -m pytest tests/test_api_cost.py tests/test_budget_coverage.py tests/unit/test_api_endpoints.py tests/test_api_auth.py tests/test_api_monitoring.py tests/test_api_versioning.py -q --no-cov --tb=short
(cd frontend && npm test && npm run build)
node frontend/scripts/verify-evaluations-live.mjs --self-test
comet classic openspec -- validate release-web-auth-acceptance --type change --strict --no-interactive
git diff --check main...HEAD
```

隔离入口为回环 HTTP。供应商密钥验证覆盖到实际 SDK 与隔离 TLS 模型列表替身。管理员的沙箱诊断 API 返回 200，API 容器的 Docker 探针状态为 `unavailable`，实际 worker 在 Docker 沙箱完成评估。隔离服务取证后均已停止。
