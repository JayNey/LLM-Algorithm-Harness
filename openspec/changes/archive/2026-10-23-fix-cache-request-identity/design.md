## 修复方案
沿用 CacheKey.generate 现有参数，追加可选 provider、base_url、generation_params；以版本 2 的排序 JSON 计算 SHA256。调用方传入未经脱敏的 effective 参数（去掉 timeout），避免凭据脱敏后碰撞。端点取 SDK 已解析的 base_url（含环境配置）；mock/无 SDK 属性时回退显式配置和服务预设。不将 API key 纳入键，不持久化原始键材料。
旧键全部失效，无需删除磁盘缓存。嵌套映射排序使相同参数顺序变化仍命中，列表顺序保留。超时、重试、API key 不改变生成语义，沿用缓存。
## 验证
先用共享临时磁盘缓存和 mock SDK 证明不同端点、provider、thinking、top_p、seed、stop、嵌套 extra_body/response_format 错误命中；修复后同参命中、异参调用 SDK，并验证配置/调用覆盖参数一致。运行相关测试、格式检查和 Python 包构建。
