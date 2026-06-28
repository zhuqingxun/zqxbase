---
## 下一步

推荐: {primary_cmd}
原因: {primary_reason}

其他选择:
{alternatives_block}

获取引导: /mint:next

<!--
# next-hints-template.md — 末尾引导块共享模板

本模板被 9 个 mint skill 末尾统一 Read 并占位符替换后输出，也被 mint:next active 聚焦模式 Read。

## 使用说明

- 读取本模板后，用 compute-next-hints 子命令输出的 JSON 填充占位符后原样输出
- alternatives_block 按每行 `- {cmd}: {when}` 循环展开；无备选时输出单行 `- 无`
- 开头的 `---` 为 Markdown 水平分隔线，**必须保留**作为与上文的视觉分隔（HINT-01 断言项）
- 模板正文中文用半角标点（`:` 而非 `：`）

## 占位符清单

| 占位符 | 填充来源 | 示例 |
|---|---|---|
| {primary_cmd} | compute_next_hints JSON primary.cmd | /mint:refine 02_示例会议 |
| {primary_reason} | compute_next_hints JSON primary.reason | 转录完成，建议清洁逐字稿提升可读性 |
| {alternatives_block} | 按 alternatives[] 数组每行 `- {cmd}: {when}` 展开 | 见下 |

## alternatives_block 展开示例

输入 JSON：

```
{
  "alternatives": [
    {"cmd": "/mint:extract --source clean", "when": "跳过 polish 直接结构化"},
    {"cmd": "/mint:status", "when": "先查看当前进度"}
  ]
}
```

展开后：

```
- /mint:extract --source clean: 跳过 polish 直接结构化
- /mint:status: 先查看当前进度
```

数组为空时输出：

```
- 无
```
-->

