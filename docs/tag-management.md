# 标签标准化与推荐

`TagManager` 将题库标签统一为 `config/tag_mapping.yaml` 中的 canonical name。别名可以包含不同平台的写法、下划线/短横线变体和中文名称，例如 `hash_map`、`hash map`、`哈希表` 都会归一化为 `hash-table`。

运行预览命令：

```bash
harness tags normalize \
  --dataset data/problems.json \
  --report results/tag-normalization.json
```

预览会输出每道题的原始标签、标准标签、未知标签、标签频次和基于标题/描述关键词的建议。命令默认不写入题库。确认建议后写入新文件：

```bash
harness tags normalize \
  --dataset data/problems.json \
  --output data/problems.normalized.json \
  --apply-recommendations
```

输入文件不会被覆盖。`--min-confidence` 控制推荐阈值，默认值为 `0.8`。推荐过程只使用本地 YAML 中的确定性关键词，不会调用模型，因此同一输入会得到相同报告。

项目可以通过 `--mapping custom-tags.yaml` 追加自己的规则。自定义文件支持以下结构：

```yaml
tags:
  segment-tree:
    aliases: [segment_tree, 线段树]
    keywords: [segment tree, 线段树]
aliases:
  range-tree: segment-tree
```

`tags` 用于声明 canonical name、别名和推荐关键词；`aliases` 适合声明少量额外别名。自定义文件会在内置映射上合并，重复 canonical name 的规则会追加别名和关键词，便于在保留通用词表的同时加入项目标签。
