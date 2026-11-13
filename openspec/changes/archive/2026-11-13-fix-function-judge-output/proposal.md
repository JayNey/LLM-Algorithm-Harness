## Why

CLI 和 Web 共用的函数判题只采集返回值。LeetCode 73、88 的样例描述修改后的参数，49 则允许组间和组内的顺序变化。三题的正确解答因此可能被判失败。关联 #478。

## What Changes

- 允许函数题声明判定某个命名输入参数的调用后值。
- 支持字符串分组的两层无序比较，保留元素次数和分组边界。
- 让新导入及现有的 LeetCode 73、88、49 记录应用对应规则。

## Capabilities

### Modified Capabilities

- `execution-protocol`：按题目的规则选择函数结果和比较输出。

## Impact

影响共享题目模型、LeetCode 导入记录的加载，以及 CLI 和 Web 使用的函数判题。既有判题配置继续有效。
