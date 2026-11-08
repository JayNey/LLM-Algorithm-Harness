## Why

在公开用例全部通过而隐藏用例全部失败时，A/B 报告将两个变体的样本通过率都算成 0%。这会误导用户对样本表现和显著性的判断。见 GitHub #397。

## What Changes

- 分别计算样本和正式结果的变体通过率、95% 差值区间与显著性检验。
- API 读取旧版报告时从原有逐题记录重算统计，供详情页直接展示。

## Capabilities

### New Capabilities

### Modified Capabilities

- `api/experiment-management` 细化 A/B 报告的统计口径及旧版报告读取规则。

## Impact

影响 A/B JSON 和 Markdown 产物及现有结果 API。详情页沿用已区分样本和正式通过率的表格。
