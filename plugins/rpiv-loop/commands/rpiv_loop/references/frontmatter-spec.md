# RPIV Frontmatter 规范

所有 rpiv-loop 技能产出的 .md 文件必须遵循此规范。

## Status 枚举值

### 流程文件（requirements/ plans/ validation/）

| 状态 | 含义 |
|------|------|
| `pending` | 新创建，未开始处理 |
| `in-progress` | 正在处理中 |
| `completed` | 处理完成 |
| `superseded` | 被新版本取代 |
| `archived` | 已归档 |

### Todo 文件（todo/）

| 状态 | 含义 |
|------|------|
| `open` | 新记录，未开始 |
| `in-progress` | 正在处理中 |
| `completed` | 已完成 |
| `archived` | 已归档 |

### 辅助文件（brainstorm-summary、research）

| 状态 | 含义 |
|------|------|
| `pending` | 新创建 |
| `completed` | 已被下游消费 |
| `archived` | 已归档 |

## Status 更新职责表（单一职责原则）

每个文件的 `completed` 转换只由一个技能负责，避免双写冲突：

| 文件类型 | → in-progress | → completed | 负责技能 |
|----------|---------------|-------------|----------|
| PRD | plan-feature | plan-feature | plan-feature 全权 |
| Plan | execute | execute | execute 全权 |
| code-review | code-review-fix | code-review-fix | code-review-fix 全权 |
| exec-report | — | system-review | system-review 负责关闭 |
| system-review | — | system-review 自身 | 自己关闭自己 |
| test-strategy | — | biubiubiu QA / 手动标记 | QA 测试完成后 |
| test-specs | — | biubiubiu QA / 手动标记 | QA 测试完成后 |
| delivery-report | — | 创建时即 completed | delivery-report / biubiubiu |
| brainstorm-summary | — | create-prd / biubiubiu | 消费后标记 |
| research | — | biubiubiu Research | 调研完成后标记 |
| todo | fix | fix | fix 全权 |

## Frontmatter 模板

### 流程文件

```yaml
---
description: "{类型}: {feature-name}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
related_files:
  - {关联文件路径}
---
```

### Todo 文件

```yaml
---
title: "{标题}"
type: issue | feature | todo
status: open
priority: high | medium | low
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
---
```

### Superseded 文件

被替代的文件需追加以下字段：

```yaml
status: superseded
superseded_by: {新版本文件路径}
```

## 格式约束

- status 值使用**连字符**分隔：`in-progress`（不是 `in_progress`）
- 时间戳使用 ISO 8601 格式：`YYYY-MM-DDTHH:MM:SS`
- `updated_at` 在每次修改文件内容或 status 时都必须更新
- `archived_at` 仅由 archive 技能在归档时设置
