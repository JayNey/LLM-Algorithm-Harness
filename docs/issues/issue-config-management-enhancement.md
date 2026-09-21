# [工程质量] 配置管理增强

## 背景与目标

当前配置文件相对扁平，多环境管理需要手动复制和修改配置文件。配置管理增强功能支持配置模板继承、环境变量灵活结合、配置验证和错误提示优化，提升配置管理的便利性和健壮性。

- 分类：工程质量
- 建议优先级：P2（中等价值，提升开发体验）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#16-配置管理增强)

## 工作范围

### 1. 配置模板和继承
- 支持基础配置模板：
  ```yaml
  # base.yaml
  model:
    provider: openai
    temperature: 0.7
  
  sandbox:
    timeout: 30
    memory_limit: 512MB
  ```
- 子配置继承并覆盖：
  ```yaml
  # prod.yaml
  extends: base.yaml
  model:
    model_name: gpt-4  # 覆盖
    temperature: 0.5   # 覆盖
  # sandbox 保持 base.yaml 的配置
  ```
- 支持多层继承（base → common → specific）

### 2. 环境变量增强
- 支持更多环境变量语法：
  ```yaml
  # 已支持
  api_key: "env:OPENAI_API_KEY"
  api_key: "${OPENAI_API_KEY}"
  
  # 新增：默认值
  api_key: "${OPENAI_API_KEY:default_key}"
  
  # 新增：条件替换
  model_name: "${MODEL_NAME:gpt-3.5-turbo}"
  ```
- 支持环境特定配置：
  ```yaml
  # config.yaml
  environment: "${ENV:development}"
  
  environments:
    development:
      debug: true
      log_level: DEBUG
    production:
      debug: false
      log_level: INFO
  ```

### 3. 加密配置字段
- 支持敏感字段加密存储：
  ```bash
  harness config encrypt --field api_key --value "sk-xxx"
  ```
- 配置文件存储加密值：
  ```yaml
  api_key: "encrypted:AES256:abc123def456..."
  ```
- 运行时自动解密（需要密钥环或环境变量）

### 4. 配置验证和错误提示
- 使用 JSON Schema 验证配置：
  ```python
  from jsonschema import validate
  
  schema = {
    "type": "object",
    "properties": {
      "model": {
        "type": "object",
        "required": ["provider", "model_name"]
      }
    },
    "required": ["model"]
  }
  
  validate(config, schema)
  ```
- 详细的错误信息：
  ```
  配置错误：config.yaml:12
  - 缺少必填字段：model.api_key
  - 建议：设置环境变量 OPENAI_API_KEY 或在配置中添加 api_key
  ```
- 配置文档自动生成：
  ```bash
  harness config docs > CONFIG_REFERENCE.md
  ```

### 5. 配置预设（Presets）
- 提供常见场景的预设配置：
  ```bash
  harness config init --preset quick-test
  harness config init --preset cost-optimized
  harness config init --preset high-accuracy
  ```

## 验收标准

- [ ] 配置继承机制正确工作
- [ ] 环境变量语法扩展正常解析
- [ ] 加密/解密功能安全可靠
- [ ] JSON Schema 验证覆盖所有配置字段
- [ ] 错误提示清晰且包含修复建议
- [ ] 配置文档自动生成完整
- [ ] 提供至少 3 个预设配置模板
- [ ] 文档更新：配置管理完整指南

## 边界

- 加密使用对称加密（AES），不涉及公钥基础设施（PKI）
- 配置文件支持 JSON 和 YAML，不支持 TOML
- 不实现图形化配置编辑器

## 依赖与关联

- 前置：#4 [修复] 密钥脱敏（已完成）
- 关联：所有功能（配置是基础）
- 后续扩展：配置版本控制和回滚

## 技术要点

### 配置继承实现
```python
def load_config_with_inheritance(path):
    config = yaml.safe_load(open(path))
    
    if 'extends' in config:
        base_path = config.pop('extends')
        base_config = load_config_with_inheritance(base_path)
        # 深度合并
        return deep_merge(base_config, config)
    
    return config

def deep_merge(base, override):
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

### 环境变量解析
```python
import os
import re

def resolve_env_vars(config):
    pattern = r'\$\{([^:}]+)(?::([^}]+))?\}'
    
    def replace(match):
        var_name = match.group(1)
        default_value = match.group(2)
        return os.getenv(var_name, default_value or '')
    
    if isinstance(config, str):
        return re.sub(pattern, replace, config)
    elif isinstance(config, dict):
        return {k: resolve_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_env_vars(item) for item in config]
    return config
```

### 配置加密
```python
from cryptography.fernet import Fernet

def encrypt_field(value, key):
    f = Fernet(key)
    encrypted = f.encrypt(value.encode())
    return f"encrypted:AES256:{encrypted.decode()}"

def decrypt_field(encrypted_value, key):
    if not encrypted_value.startswith('encrypted:AES256:'):
        return encrypted_value
    
    f = Fernet(key)
    encrypted = encrypted_value.split(':', 2)[2]
    return f.decrypt(encrypted.encode()).decode()
```

### JSON Schema 验证
```python
from jsonschema import validate, ValidationError

def validate_config(config):
    try:
        validate(config, CONFIG_SCHEMA)
    except ValidationError as e:
        # 生成友好的错误消息
        field_path = '.'.join(str(p) for p in e.path)
        message = f"配置错误：{field_path}\n"
        message += f"- {e.message}\n"
        message += generate_suggestion(e)
        raise ConfigError(message)
```

## 预期收益

- 实现工作量：约 5-7 天
- 开发效率：减少配置管理时间 50%
- 用户体验：配置错误更容易发现和修复
- 安全性：敏感信息加密存储

## 扩展方向

1. **配置 UI**：图形化配置编辑器（Web UI）
2. **配置模板市场**：社区共享配置模板
3. **配置版本控制**：Git 集成，配置历史追踪
