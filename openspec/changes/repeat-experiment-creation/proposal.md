## Why

首次创建实验后，会话级状态保留创建回执。用户返回列表并再次进入创建页时，无法开启新草稿。参见 [#395](https://github.com/JayNey/LLM-Algorithm-Harness/issues/395)。

## What Changes

- 在已确认的创建回执中提供开启新草稿的操作，并保留原实验详情链接。
- 保留提交进行中及结果未知时的防重处理。离开页面或重置草稿时不发送创建请求。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/app-shell` 增加同一会话连续创建实验的验收场景。

## Impact

影响实验创建页、会话级创建 store、中英文文案及浏览器 fixture。
