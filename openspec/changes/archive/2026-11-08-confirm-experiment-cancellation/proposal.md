## Why

[#414](https://github.com/JayNey/LLM-Algorithm-Harness/issues/414) 中，实验列表和详情直接提交取消请求，误触会中止排队、运行或暂停的实验。请求失败时，界面也可能保留过时的操作状态。

## What Changes

- 列表与详情使用相同的确认弹窗，支持键盘打开、按 Esc 关闭及返回。
- 确认时按关联任务 ID 提交一次。请求结束后重新读取服务端状态，按刷新结果显示状态及允许的操作。

## Capabilities

### Modified Capabilities

- `frontend/experiments-management` 增补取消确认、重复提交和失败后刷新场景。

## Impact

实验前端页面、共享确认交互、中英文文案及浏览器验收脚本。
