# 修复 #367：批量导入保留完整失败生命周期

## Why

详情抓取把失败放在 transform_failures，转换入口重置同一列表，CLI 因而错误显示 Failed=0 并成功退出。修复抓取到报告的完整生命周期，保持 CLI 参数和失败退出码契约。

## What Changes

抓取失败和转换失败分开保存。每轮 fetch 开始重置两类失败；transform 仅重置本次转换失败。兼容 transform_failures 汇总读取，使现有 CLI 和调用者仍能一次取得全部失败。直接重复 transform 不追加旧转换失败，重复 fetch（含失败和空结果）不带入旧轮次。用受控 HTTP 响应替身执行真实抓取、转换、验证、报告、main/退出，覆盖部分/全部失败及成功。全失败按既有契约普通/strict 均 exit2；部分失败普通1、strict3。

## Impact

基于已通过全部 CI 的 main `c9ae420`。无未合并前置依赖；各自独立分支和 PR。仅本 issue 的实现、测试及说明；不引入数据库或网络服务。

## 执行授权

用户要求完成新分配 issues，沿用“别问我了，自己按照推荐做完”、独立 worktree/PR 和独立审查偏好。采用局部 hotfix 预设；先实际 RED 后修复，最终 standard 独立审查。
