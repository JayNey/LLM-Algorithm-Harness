# 资料与密钥读取恢复验证报告

2026-11-09，结论 PASS。实现提交 `f1ae5492`。[Issue #425](https://github.com/JayNey/LLM-Algorithm-Harness/issues/425)

## 完整性

OpenSpec 完成 1/1 任务。个人资料、API 密钥管理和基准套件管理的三份增量规格通过严格校验。实现范围为三个页面、中英文提示和一份浏览器回归脚本，共六个前端文件。

## 正确性

- 资料请求返回 500 时提供原页重试。重试返回空数据时显示独立提示。接口恢复后表单重新载入资料并可编辑。
- 密钥管理页区分首次加载失败和成功空列表。新增、改名和删除分别验证了写入成功、回读返回 500、成功和失败提示同时可见、重试只增加一次 GET。添加成功后清空密钥输入。
- 基准运行表单的密钥读取返回 500 时禁用选择与启动。重试只请求密钥列表。成功空列表有独立提示，返回密钥后可用键盘选择。
- 模拟账号切换和路由离开时，旧列表请求取消，当前列表只显示当前作用域的记录。

## 一致性

实现沿用会话标识、HTTP 会话校验和可取消的读取流程。写入结果独立于列表状态。Tweak 使用 change 内的精简设计和默认的 `review_mode: off`，已逐项对照代码、规格和测试结果。

## 执行结果

- `npm run lint`、`npm run build`、`npm test` 通过，单测 341 项。构建提示部分产物分块大于 500 kB。
- `node scripts/verify-account-load-retry.mjs` 在 Vite 开发服务和本地 Chrome 中通过九个模拟 API 场景。人工检查了 480 像素宽度下并列的成功和失败提示。
- `node scripts/verify-direct-load.mjs` 在生产构建上通过 67 项断言，未发现未声明请求。
- `comet classic openspec -- validate fix-settings-key-load-retry --strict` 和 `git diff --check` 通过。

## 归档复核

三份主规格均通过常规校验。对主规格运行严格校验时，基准管理仍有历史 Purpose 占位提示，个人资料仍有历史 Purpose 长度提示。两处 Purpose 与基线一致。
