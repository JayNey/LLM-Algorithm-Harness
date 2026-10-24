# 验证报告：problems-frontend（issue #163：题目管理页，真实契约子集）

- 日期：2026-10-24
- 分支：comet/problems-frontend（交付目标 tweak/20261024/problems-frontend）
- 基线：d0f275c（upstream/main），6 个提交，约 12 文件
- 验证模式：full（1 份 delta spec；用户沿前两步先例继续 tweak——同类自包含前端簇）
- 集成审查：两轮制。第一轮 REQUESTS_CHANGES：**2 P0**（`/files/upload` 响应按臆测顶层键解析——异步通道必炸；`validation.errors` 形状 `{index,error}` 不存在，真实为 `{index,errors:[{field,type}]}`——含无效条目的导入报告必炸；mock 同形掩盖，复审方以「对着臆测形状写码」定性）+ 4 P1（轮询失败静默卡死、失败终态 result 形状、浮点进度、YAML 白名单）+ 7 P2 → c129df9 全部修复 → 定点复审 **APPROVE**（3 条不阻塞残留：R-1/R-2 已在 83952d1 顺手修复——submit 重置轮询计数、failureDetail 支持 {message} 字典 detail；R-3 记录于 design.md）。

## 1. Completeness

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| tasks.md 8/8 全部勾选 | PASS | 未勾选 0 |
| delta spec 3 条需求（元数据浏览/导入/导出与历史） | PASS | 见 §2 |
| proposal 目标（真实契约子集）满足，不做假入口 | PASS | 无搜索/标签筛选/详情/编辑删除/平台抓取入口（审查项 7 核实） |

## 2. Correctness：需求与场景映射

| Spec 需求 | 实现 | 场景覆盖 |
| --- | --- | --- |
| 题库元数据浏览（分页/来源筛选回 URL/计数徽标/仅 4 字段） | ProblemsPage + client 严格解析 | client.test（夹带敏感字段只取元数据 deepEqual、缺字段拒绝、URL 白名单 round-trip）；verify list 场景 |
| 个人题库导入（双通道/validation 报告/overwrite 确认/后端拒绝如实展示） | ImportPanel | client.test（直导报告含嵌套错误明细、异步链路三端点、失败终态 {status_code,detail}→failureDetail、浮点进度）；verify import 场景（含 `description（missing）` 渲染断言） |
| 导出与评估历史 | exportUrl + HistoryDrawer | client.test（历史条目可空指标）；verify history 场景（通过率 50% 聚合）；抽屉关闭短路（owner 空串） |

## 3. Coherence

- design.md 契约盘点经勘误后与实现一致（两处 P0 根因即原盘点记录错误）；复审备注记录 R-3 与 verify 异步场景后续项。
- 四簇既定模式（严格解析/session/useList/表格样式）同构复用；AppLayout 第五层 provider 嵌套正确（审查项 8）。
- multipart 字段名/validate 字符串、防泄漏测试、URL 回填、useList 桥接、导出凭据携带均经审查逐项核实无问题。

## 4. Runtime 检查证据

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| build/verify：`bash -lc 'cd frontend && npm test'` | exit=0 | .comet/checks/0a740d1d 与后续最新日志（217 tests 全过；复审方独立重跑一致） |
| lint / type | PASS | tsc -b 0 错误；eslint（簇/页面/verify 脚本）0 problems；prettier 通过 |
| 安全 | PASS | 元数据外字段不渲染（测试锁定）；导出同源带 Cookie；无注入面；无新增依赖 |

## 5. 限制与偏差声明

- verify 异步导入场景（upload→import→polling）未加入脚本——Playwright 环境不可用；链路由 client.test 覆盖，列为环境恢复后后续项（design.md 备注）。
- R-3：异步轮询期间用户可收起面板（服务端继续、本页不再刷新），属产品权衡已记录。
- 全部条目无效的同步导入 400 错误经共享 http.ts 退化为通用文案（P2-4 审查接受为共享层限制，PR 描述注明）。

## 结论

三维验证无 CRITICAL、无 WARNING；两轮审查最终 APPROVE 且残留已处理。**验证通过，可进入归档确认。**
