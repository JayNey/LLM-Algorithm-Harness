## Context

见 proposal。探索 iteration 记录父节点；共享工厂默认取最后 iteration 的代码，故不能代表最终叶子。

## Goals / Non-Goals

保证 ToT 返回代码与最终评测对象一致；不修改其他策略或独立 S02 计费问题。

## Decisions

- 保留探索历史，ToT 在创建结果后显式设置 generated_code，避免伪造探索 iteration 或改变共享工厂 API。
- 叶子候选过滤空白代码；无可用叶子返回 code_extraction_failed 并清空结果代码，防止历史父节点被正式判题。
- 公开执行失败或沙箱异常仍保留所选代码与失败状态，维持 Harness 的独立 hidden 评测机制。
- 回归使用真实 ToT 与 Harness，仅模型和沙箱替换为确定性响应。

## Risks / Trade-offs

显式赋值绕过工厂默认值 → 以单层、多层、BFS/DFS、两种兄弟顺序及失败路径覆盖契约。
