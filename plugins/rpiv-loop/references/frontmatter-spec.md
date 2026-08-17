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

### Handoff 文件（handoff-*）

跨会话长程任务交接文件，状态机仅 2 状态（`pending`/`archived` 均为 process 状态集子集，但**不走** `in-progress`/`completed`/`superseded`）：

| 状态 | 含义 |
|------|------|
| `pending` | 新创建，待下次会话消费 |
| `archived` | 已被新会话消费（通过 `/rpiv-loop:handoff --mark-consumed`） |

**特殊字段**：`consumed_at` (ISO 时间戳，mark-consumed 时填写)

**hook 校验**：`validate_rpiv_status.py` 对 handoff 文件按独立 `handoff` 类目校验（合法 status 仅 `pending` / `archived`）。识别依据（按优先级）：① frontmatter `type` 显式为 `handoff` → handoff；显式为 `todo`/`issue`/`feature` → 按 todo 枚举（避免"关于 handoff 的 todo"被误判，如 `todo-xxx-handoff-yyy`）；② type 缺失时按文件名——仅 `handoff-*` 前缀或 `*-handoff`/`*-HANDOFF` 后缀判 handoff（**不是**含 `handoff` 子串），优先于 `rpiv/todo/` 路径规则。handoff 物理常落在 `rpiv/todo/` 下且常无 `type` 字段，必须靠文件名前后缀先识别为 handoff，否则合法的 `pending` 会被误拒。

**与其他流程文件区别**：
- 不走 `in-progress` / `completed` / `superseded` 状态（handoff 是一次性票据语义）
- 不写 `supersedes` / `superseded_by` 字段（演化追溯靠文件名时间序）
- 归档动作不需要 `/rpiv-loop:archive`（mark-consumed 即归档）

详见 `skills/handoff/SKILL.md`。

## Status 更新职责表（单一职责原则）

每个文件的 `completed` 转换只由一个技能负责，避免双写冲突：

| 文件类型 | → in-progress | → completed | 负责技能 |
|----------|---------------|-------------|----------|
| PRD | plan-feature | plan-feature | plan-feature 全权 |
| Plan | execute | execute | execute 全权 |
| code-review | code-review-fix | code-review（干净通过自闭合）/ code-review-fix（修复后） | 两条互斥路径，见表下注 |
| exec-report | — | 创建时即 completed | execution-report（事实记录，自闭合） |
| test-strategy | — | biubiubiu QA / 手动标记 | QA 测试完成后 |
| test-specs | — | biubiubiu QA / 手动标记 | QA 测试完成后 |
| delivery-report | — | 创建时即 completed | delivery-report / biubiubiu |
| brainstorm-summary | — | create-prd / biubiubiu | 消费后标记 |
| research | — | biubiubiu Research | 调研完成后标记 |
| todo | fix | fix | fix 全权 |

> **注（code-review 的两条互斥闭合路径）**：code-review 创建文件为 `pending`。① 审查**发现需修复问题**（critical/high/medium 等 `status: open` 项）→ 保持 `pending`，由 `code-review-fix` 修复后翻 `completed`（其 step 4）。② 审查**干净通过**（仅输出"代码审查通过"或 low/by-design 等无需修复的观察）→ `code-review-fix` 不会触发，由 `code-review` **自身**在产出时直接翻 `completed`。两条路径互斥（一次审查非此即彼），不构成双写，仍满足单一职责。

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

### Superseded 文件（仅流程文件）

**仅流程文件**（requirements/ plans/ validation/）支持 `superseded`——它们有版本血缘（PRD/Plan v1 被 v2 取代）。被替代的文件追加以下字段：

```yaml
status: superseded
superseded_by: {新版本文件路径}
```

**典型场景**：
- 流程文件：PRD/Plan v1 被 v2 取代（plan-feature 阶段触发）
- 后续动作：superseded 是终态前置——可由 archive 技能正常归档（与 completed 等价）

**Todo / 辅助文件不支持 superseded**：
- **Todo**：轻量高频工件，不设 superseded 子状态。旧待办因范围扩大重立 / 合并到其他特性时**直接归档**（`status: archived`，可追加 `superseded_by` 作为追溯笔记）。hook 拒绝 todo 的 superseded；`flow_status` 一致性检查会把误标 superseded 的 todo 自动归一化为 `archived`（保留 `superseded_by`）。
- **辅助文件**（brainstorm-summary / research）：状态机仅 `pending / completed / archived`，被消费即 completed，无 superseded。

**边缘场景：一对多拆解**

骨架流程文件（或 todo）被拆解为多个具体条目时，单值 `superseded_by` 不足以表达（todo 本就不走 superseded，直接归档）。两种处理方式：
- **优先做法**：直接归档（status: archived），追溯关系由正文叙述承担。骨架级 draft 的最终归宿就是归档，规范化字段无未来收益（YAGNI）
- **如确需结构化追溯**：用 `superseded_by_note: "..."` 字符串字段简述被哪些文件拆解，避免 `superseded_by` 字段类型变更带来的工具链改造

不引入 `superseded_by: array<string>` 类型扩展——仅在出现稳定多次"一对多拆解"案例时再讨论是否升级字段定义。

## 产物类型字段（product_types）

PRD 文件（`requirements/prd-*.md`）的**可选** frontmatter 字段，声明本次交付的产物类型，供 plan-feature / validate / code-review 做分支分派。

| 取值 | 含义 |
|------|------|
| `code` | 可执行代码产物（默认） |
| `skill` | SKILL.md / references 等技能定义产物 |

```yaml
product_types: [code]          # 纯代码（等价于省略该字段）
product_types: [skill]         # 纯 skill
product_types: [code, skill]   # 混合产物，两套质量门取并集
```

**三条契约**：

1. **仅 PRD 使用**：plan / validation / todo / handoff 等其他文件类型不写此字段；下游技能一律从 PRD 读取
2. **hook 不校验**：`hooks/validate_rpiv_status.py` 只提取 `status` 与 `type` 两个字段，`product_types` 的取值与格式由使用它的技能自行判断，写错不会被 Write/Edit 拦截
3. **缺失默认 `[code]`**：存量 PRD 无需回填，所有纯代码流程行为与该字段引入前完全一致

skill 场景的具体指引见 `references/skill-authoring/`（由 create-prd / plan-feature / validate 按需加载）。

## 格式约束

- status 值使用**连字符**分隔：`in-progress`（不是 `in_progress`）
- 时间戳使用 ISO 8601 格式：`YYYY-MM-DDTHH:MM:SS`
- `updated_at` 在每次修改文件内容或 status 时都必须更新
- `archived_at` 仅由 archive 技能在归档时设置
