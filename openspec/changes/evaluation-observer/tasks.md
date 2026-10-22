# Tasks: evaluation-observer

## 1. 测试先行（issue Step 1–2）

- [x] 1.1 新增 `frontend/src/evaluations/observer.test.ts`：FakeClock/FakeSocket/调用记录基建 + 全边界用例（URL 解析、启动与 5s 订阅确认、2s 合并、非重叠单周期、15s live 兜底、3s 降级轮询、3/6/12/30 退避与 5 次上限、429≥30s、终态/paused 收敛、4403 清数据、401/4401 recoverSession、隐藏/离线暂停恢复、mutation epoch、dispose 清理），运行确认 RED
- [x] 1.2 运行 `node --experimental-strip-types --test src/evaluations/observer.test.ts` 并在 issue 记录 RED 证据（退出码、失败清单），不得靠真实 sleep 跑时间边界

## 2. 实现（issue Step 3）

- [ ] 2.1 `resolveProgressWsUrl`：相对路径 http→ws / https→wss，绝对 ws(s) 直通
- [ ] 2.2 `createProgressObserver` 生命周期核心：start 幂等、立即刷新、connectSocket、subscribe、5s 确认定时器、connected/subscribed/事件帧分发
- [ ] 2.3 事件失效与刷新管线：2s 合并窗口、pending 一次失效、非重叠单周期、signal.aborted 与 epoch 守卫、HTTP 真值经 onChange('snapshot')
- [ ] 2.4 降级与重连：WS 失败进 degraded 3s 轮询、3/6/12/30 退避、5 次上限后放弃 WS、成功清零、15s live 无事件兜底刷新、429 顺延
- [ ] 2.5 终态与权限与会话：终态/paused 停止 + settled、4403/403/404 清数据停止、401/4401 走 recoverSession 成败两路
- [ ] 2.6 暂停与清理：setVisible/setOnline 暂停恢复（恢复清零重连计数）、runMutation epoch、dispose 后无任何回调
- [ ] 2.7 全量测试转绿；`npm run lint`（或 eslint 定向）与 prettier 检查通过

## 3. 验收记录（issue Step 5 的核心部分）

- [ ] 3.1 在 #225 记录 Step 1–3 验收结果（测试命令、退出码、时序边界覆盖清单），声明 Step 4 等 #224；提交关联 PR
