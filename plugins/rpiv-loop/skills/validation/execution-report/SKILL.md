---
name: rpiv-loop:validation:execution-report
description: >-
  为系统审查生成实施报告
allowed-tools: Read, Bash, Grep, Glob, Write
version: 2.1.2
---

# 执行报告

审查并深入分析您刚刚完成的实施。

## 上下文

您刚刚完成了一个功能的实施。在继续之前，反思：

- 您实施了什么
- 它如何与计划对齐
- 您遇到了什么挑战
- 什么偏离了计划以及原因

## 生成报告

保存到：`rpiv/validation/exec-report-{kebab-case-feature-name}.md`

- 如果 `rpiv/validation/` 目录不存在则创建

### 文件格式

文件必须包含 YAML frontmatter 和内容：

```markdown
---
description: "执行报告: {feature-name}"
status: completed
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
related_files:
  - {plan-file-path}  # 从上下文或命令参数获取关联的计划文件路径
---

# 执行报告

{报告内容}
```

**Frontmatter 字段说明：**
- `description`: 文件描述
- `status`: 执行报告是事实记录，创建完成即为 `completed`
- `created_at`: 创建时间戳，ISO 8601 格式
- `updated_at`: 更新时间戳，创建时与 created_at 相同
- `archived_at`: 归档时间戳，创建时固定为 `null`
- `related_files`: 关联文件列表，至少包含关联的计划文件路径

### 元信息

- 计划文件：[指导此实施的计划路径]
- 添加的文件：[带路径的列表]
- 修改的文件：[带路径的列表]
- 更改的行数：+X -Y

### 验证结果

- 语法和代码检查：✓/✗ [如果失败，详细信息]
- 类型检查：✓/✗ [如果失败，详细信息]
- 单元测试：✓/✗ [X 通过，Y 失败]
- 集成测试：✓/✗ [X 通过，Y 失败]

### 进展顺利的部分

列出进展顺利的具体事项：

- [具体示例]

### 遇到的挑战

列出具体困难：

- [什么困难以及原因]

### 与计划的偏离

对于每个偏离，记录：

**[偏离标题]**

- 计划：[计划指定的内容]
- 实际：[实际实施的内容]
- 原因：[为什么发生此偏离]
- 类型：[发现更好的方法 | 计划假设错误 | 安全问题 | 性能问题 | 其他]

### 跳过的项目

列出计划中未实施的内容：

- [跳过的内容]
- 原因：[为什么跳过]

### 建议

基于此实施，下次应该改变什么？

- 计划命令改进：[建议]
- 执行命令改进：[建议]
- CLAUDE.md 添加：[建议]
