# 提议：从 LeetCode 导入题面、元数据与公开样例

## Problem

当前题库导入器只支持本地 JSON。用户需要手写题面、来源和公开样例，且没有对网络失败、题目不存在、受限题目和页面结构变化的统一处理。

## Goal

- 接受 LeetCode 题目 URL 或 slug，通过公开题目接口获取题面和元数据。
- 清洗 HTML，保留代码、公式和约束的含义。
- 可靠解析的公开样例才进入 `public_test_cases`；无法确定输入或期望输出时标记人工补全，不伪造数据。
- 复用现有导入器的预览、校验、去重、覆盖和原子写入流程。
- 用离线响应夹具覆盖多种签名和样例形态，在线验证可选且不阻塞离线测试。

## Scope

- 新增 `LeetCodeImporter`，只支持 `leetcode.com` 的公开题目 URL/slug。
- 处理超时、限流、认证/权限、题目不存在、GraphQL 错误和结构变化。
- 将导入结果记录为 LeetCode 来源、版本和 public-only/人工补全状态。
- 注册 `harness import --source leetcode` 并更新文档。

## Non-goals

- 不绕过登录、付费限制、验证码或反爬验证。
- 不获取或声称获取官方隐藏测试，不自动提交代码。
- 不实现 LeetCode 链表、树或交互题的复杂序列化。

## Impact

- 影响 `src/importers`、`src/main.py`、`src/models.py`、导入文档和测试夹具。
- 网络访问只发生在显式 `import --source leetcode` 调用中；普通评测不依赖网络。
