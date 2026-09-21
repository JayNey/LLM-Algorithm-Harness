# [功能] Codeforces 题目导入器

## 背景与目标

当前仅支持 LeetCode 和 LiveCodeBench 题目导入，题库规模有限。Codeforces 是全球最大的算法竞赛平台之一，拥有数千道高质量题目和完整的测试数据，扩展该数据源可显著丰富评估覆盖率。

- 分类：数据源集成
- 建议优先级：P1（实现成本低，收益明显）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#5-更多数据源集成)

## 工作范围

### 1. Codeforces API 集成
- 使用 Codeforces API 获取题目列表
  - API 端点：`https://codeforces.com/api/problemset.problems`
  - 获取题目基本信息（ID、标题、难度评级、标签）
- 爬取题目详情页面
  - 题目描述（中英文支持）
  - 输入输出格式说明
  - 样例输入输出
  - 数据范围和约束

### 2. Schema 转换
- 将 Codeforces 数据转换为标准 `Problem` schema
  - `problem_id`: `codeforces_{contestId}_{index}`（如 `codeforces_1234_A`）
  - `title`: 题目标题
  - `description`: 完整题目描述
  - `difficulty`: 映射规则（见下方）
  - `tags`: Codeforces 标签映射
  - `public_tests`: 公开样例
  - `hidden_tests`: 从题目约束生成基础测试

### 3. 难度映射
Codeforces 难度评级（800-3500）映射到标准三级：
- Easy: 800-1400
- Medium: 1500-2100
- Hard: 2200+

### 4. CLI 命令
```bash
# 导入指定 contest 的题目
harness import codeforces --contest 1234 --output data/codeforces.json

# 按难度过滤导入
harness import codeforces --min-rating 1500 --max-rating 2000 --limit 50

# 按标签过滤
harness import codeforces --tags "dp,greedy" --limit 30
```

## 验收标准

- [ ] `src/importers/codeforces_importer.py` 实现完整
- [ ] 成功导入至少 50 道题目并转换为标准格式
- [ ] 转换后的题目通过 schema 验证
- [ ] 样例测试用例正确解析
- [ ] CLI 命令正常工作，支持过滤参数
- [ ] 单元测试覆盖主要功能
- [ ] 文档更新：导入器使用说明，Codeforces 题目特点

## 边界

- 仅导入公开题目，不涉及账号登录或私有题库
- Hidden tests 基于约束自动生成，不保证覆盖所有边界情况
- 不处理交互式题目（Interactive Problem）
- 题目描述保留原始格式，不做深度解析（如 LaTeX 公式）

## 依赖与关联

- 前置：#6 [功能] 题目 Schema（已完成，复用标准 Schema）
- 参考：LeetCode 和 LiveCodeBench 导入器实现
- 后续扩展：HackerRank、AtCoder 导入器

## 技术要点

### API 调用示例
```python
import requests

def fetch_problems():
    url = "https://codeforces.com/api/problemset.problems"
    response = requests.get(url)
    data = response.json()
    problems = data['result']['problems']
    return problems
```

### 题目详情爬取
- 使用 BeautifulSoup 解析 HTML
- 目标 URL：`https://codeforces.com/problemset/problem/{contestId}/{index}`
- 提取 `.problem-statement` 区块内容

### 难度映射
```python
def map_difficulty(rating: int) -> str:
    if rating < 1500:
        return "Easy"
    elif rating < 2200:
        return "Medium"
    else:
        return "Hard"
```

### 标签映射
Codeforces 标签 → 标准标签：
- `dp` → `dynamic-programming`
- `greedy` → `greedy`
- `graphs` → `graph`
- `trees` → `tree`
- `math` → `math`

## 预期收益

- 实现工作量：约 2-3 天
- 题库扩展：+1000 道高质量题目
- 难度覆盖：更多 Hard 级别竞赛题
- 用户价值：丰富评估场景，更全面的模型能力测试
