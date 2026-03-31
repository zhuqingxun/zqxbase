---
name: rpiv-loop:flow-status
description: 查看过程文件的状态
allowed-tools: Read, Bash, Glob, Grep, AskUserQuestion
version: 2.1.3
---

# Status: 查看文件状态

显示过程文件的当前状态,帮助管理开发流程。

## 用法

```bash
/rpiv-loop:flow-status              # 精简摘要（默认）
/rpiv-loop:flow-status all          # 按特性聚合的完整表格
/rpiv-loop:flow-status pending      # 只显示待处理文件
/rpiv-loop:flow-status in-progress  # 只显示进行中文件
/rpiv-loop:flow-status completed    # 只显示已完成文件
/rpiv-loop:flow-status feature-name # 某个特性的详细状态
/rpiv-loop:flow-status check        # 一致性检查,报告异常
/rpiv-loop:flow-status fix          # 交互式修复状态异常
```

## 执行逻辑

### 数据采集（所有模式共用）

1. 扫描以下位置的 .md 文件：
   - `rpiv/requirements/`、`rpiv/plans/`、`rpiv/validation/`、`rpiv/todo/`
   - `rpiv/` 根目录下匹配 `brainstorm-summary-*.md` 和 `research-*.md` 的辅助文件
2. 读取 frontmatter 的 status, type, created_at, updated_at, related_files（todo 使用 title 字段）
3. 从文件名提取名称（去掉 `prd-`/`plan-`/`code-review-`/`exec-report-`/`system-review-`/`delivery-report-`/`test-strategy-`/`test-specs-`/`brainstorm-summary-`/`research-` 前缀；todo 文件去掉 `issue-`/`feature-`/`todo-` 前缀）
4. 扫描 `rpiv/archive/` 统计已归档文件数
5. **Status 值合法性校验**（参见 `~/.claude/skills/rpiv-loop/references/frontmatter-spec.md`）：
   - 流程文件允许：`pending` / `in-progress` / `completed` / `superseded` / `archived`
   - Todo 文件允许：`open` / `in-progress` / `completed`
   - 辅助文件允许：`pending` / `completed`
   - 不合法的值（如 `in_progress`、`delivered`、空值）标记为异常

### 模式 0: 精简摘要（无参数,默认）

**输出结构（严格按此顺序）：**

1. **一行式计数摘要** — 所有状态计数在一行内
2. **异常区块**（仅当存在异常时显示）— 一致性检查发现的问题,附修复命令
3. **进行中区块**（仅当存在时显示）— 每个 in-progress 文件一行,含文件名和描述
4. **待处理区块**（仅当存在时显示）— 每个 pending 文件一行
5. **已完成区块**（仅当存在时显示）— 按特性聚合,每特性一行,列出各阶段完成状态
6. **已归档区块**（仅当存在时显示）— 按特性聚合,每特性一行

**输出示例：**

```
## 流程状态

⚠️ 异常 1 | 🔄 进行中 1 | ⏳ 待处理 0 | ✓ 已完成 2 | 📦 已归档 2 | 📋 Todo 3

### ⚠️ 异常
- prd-user-auth.md [in-progress] — 关联 Plan 已完成,建议更新 → `/rpiv-loop:flow-status fix`

### 🔄 进行中
- plan-tray-flash.md — 托盘闪烁提醒 [Plan]

### ✓ 已完成（建议归档 → `/rpiv-loop:archive all`）
- tray-flash-notification — PRD ✓ Plan ✓
- user-auth — PRD ✓ Plan ✓ Review ✓

### 📋 Todo（open: 3 | in-progress: 1 | completed: 0）
#### 🐛 Issue
- [open] chrome-extension-windows-bug — Claude Code Chrome 扩展连接失败
#### ✨ Feature
- [open] batch-export — 批量导出功能
- [in-progress] exclusion-rules — 排除规则功能
#### 📝 Todo
- [open] migrate-config — 迁移配置文件

### 📦 已归档
- smile-msg — PRD ✓ Plan ✓
```

**规则：**
- 计数为 0 的区块不显示（异常为 0 时隐藏异常区块,以此类推）
- 一行式计数摘要始终显示
- 无 frontmatter 的文件归入单独的"未跟踪"区块（仅当存在时）

### 模式 1: 完整表格 (`/rpiv-loop:flow-status all`)

按特性聚合为表格,每特性一行:

```
## 全部特性状态

| 特性 | PRD | Plan | Review | Exec | System | Delivery | 状态 |
|------|-----|------|--------|------|--------|----------|------|
| tray-flash-notification | ✓ | ✓ | — | — | — | — | 可归档 |
| user-auth | ✓ | 🔄 | — | — | — | — | 进行中 |
| new-feature | ⏳ | — | — | — | — | — | 待处理 |

📦 已归档: smile-msg (PRD + Plan)

未跟踪: old-prd.md, old-plan.md
```

**表格符号:** ✓ completed, 🔄 in-progress, ⏳ pending, — 不存在

### 模式 2: 按状态过滤 (`/rpiv-loop:flow-status {status}`)

只显示指定状态的文件,每文件一行,含路径:

```
## 🔄 In Progress (2 个)

- plan-tray-flash.md → rpiv/plans/plan-tray-flash-notification.md
  更新于 2026-01-28 08:00
- exec-report-work.md → rpiv/validation/exec-report-work.md
  更新于 2026-01-28 08:30
```

### 模式 3: 特性详情 (`/rpiv-loop:flow-status feature-name`)

该特性的所有文件详细信息（这是唯一展示完整时间戳的视图）:

```
## 特性: user-auth

| 阶段 | 文件 | 状态 | 创建 | 更新 |
|------|------|------|------|------|
| Brainstorm | brainstorm-summary-user-auth.md | ✓ | 01-24 14:00 | 01-25 09:00 |
| Research | research-user-auth.md | ✓ | 01-24 15:00 | 01-25 08:00 |
| PRD | prd-user-auth.md | ✓ | 01-25 10:00 | 01-26 16:00 |
| Plan | plan-user-auth.md | ✓ | 01-26 10:00 | 01-27 14:00 |
| Exec Report | exec-report-user-auth.md | ✓ | 01-27 14:30 | 01-27 15:00 |
| Code Review | code-review-user-auth.md | ✓ | 01-27 15:00 | 01-27 16:00 |
| System Review | system-review-user-auth.md | ✓ | 01-27 16:00 | 01-27 16:30 |
| Delivery | delivery-report-user-auth.md | ✓ | 01-27 17:00 | 01-27 17:00 |

✓ 状态一致性检查通过

建议归档 → `/rpiv-loop:archive user-auth`
```

### 模式 4: 一致性检查 (`/rpiv-loop:flow-status check`)

检查规则:

| 条件 | 异常判定 |
|------|----------|
| Plan 为 completed 或 in-progress | 关联的 PRD 应为 completed |
| Validation 文件为 completed | 关联的 Plan 应为 completed |
| 文件状态为 in-progress 超过 48 小时 | 警告: 可能是会话中断导致的悬停 |
| Status 值不在合法枚举内 | 异常: 非标准状态值，需修正 |
| 同一特性存在 V1 和 V2 文件且 V1 非 superseded/archived | 异常: 版本替代未处理 |
| brainstorm-summary 存在但无对应 PRD | 提示: 需求摘要未推进 |
| todo status=completed 但无对应的修复记录或 PRD | 警告: 完成标记可能不准确 |
| todo status=completed 仍在 rpiv/todo/ 中 | 异常: 已完成的 todo 应归档 → `/rpiv-loop:archive rpiv/todo/{name}.md` |
| exec-report 存在但 Plan 不是 completed | 异常: 执行报告先于计划完成 |

输出: 仅列出异常项,无异常则输出 `✓ 全部一致,无异常`

### 模式 5: 自动修复 (`/rpiv-loop:flow-status fix`)

1. 先运行一致性检查
2. 可自动修复的直接执行（PRD 状态落后于 Plan → 自动更新）
3. 需用户决策的用 AskUserQuestion 询问（如 in-progress 超 48 小时 → 完成/回退/保持）

## 实现说明

- 只扫描 .md 文件,不递归子目录
- 不缓存,每次实时读取
- 按 updated_at 降序排列
- 状态符号: ⏳ pending, 🔄 in-progress, ✓ completed, ⏪ superseded, 📦 archived
- 辅助文件（brainstorm-summary、research）在精简摘要中归入独立的"📝 辅助文件"区块显示
- Status 合法性规则参见 `~/.claude/skills/rpiv-loop/references/frontmatter-spec.md`
