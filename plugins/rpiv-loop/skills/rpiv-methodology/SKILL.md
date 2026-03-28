---
name: rpiv-loop
description: >-
  RPIV 结构化开发方法论——四阶段功能开发流程(需求→计划→实施→验证)。
  当用户的项目安装了此插件时，自动加载 RPIV 方法论上下文。
---

# RPIV 开发方法论

你是一名熟悉 RPIV 四阶段开发流程的 AI 助手。当用户的项目安装了此插件时，你应理解并遵循 RPIV 方法论来组织功能开发。

## 四阶段模型概述

RPIV 是一套结构化的功能开发流程，将开发过程分为四个阶段，每个阶段有明确的输入、输出和质量门禁：

```
需求（R） → 计划（P） → 实施（I） → 验证（V）
  ↑                                      ↓
  └──────────── 经验反馈 ────────────────┘
```

| 阶段 | 核心问题 | 输入 | 输出 |
|------|---------|------|------|
| **R - 需求** | 做什么？为什么做？ | 对话/想法 | `rpiv/requirements/prd-{name}.md` |
| **P - 计划** | 怎么做？按什么顺序？ | PRD + 代码库分析 | `rpiv/plans/plan-{name}.md` |
| **I - 实施** | 把计划变成代码 | 计划文件 | 代码文件 + 测试文件 |
| **V - 验证** | 做得对不对？好不好？ | 实施结果 + 计划 | 审查报告 |

### 核心价值

- **阶段边界清晰**：每阶段有明确的输入和输出，避免混乱
- **决策前置**：在成本最低的时候做最重要的决策
- **质量内建**：质量在每个阶段构建，而非最后检查
- **可复盘**：完整的过程记录让问题定位和经验总结成为可能

## 过程文件规范

### 目录结构

```
rpiv/
├── requirements/          # PRD 文档
│   └── prd-{name}.md
├── plans/                 # 实施计划
│   └── plan-{name}.md
├── validation/            # 验证报告
│   ├── code-review-{name}.md
│   ├── exec-report-{name}.md
│   └── system-review-{name}.md
├── todo/                  # 待办条目
│   ├── issue-{name}.md
│   ├── feature-{name}.md
│   └── todo-{name}.md
└── archive/               # 已归档文件
```

### Frontmatter 规范

所有过程文件必须包含 YAML frontmatter：

```yaml
---
description: "文档类型: {feature-name}"
status: pending          # pending → in-progress → completed → archived
created_at: YYYY-MM-DDTHH:MM:SS
updated_at: YYYY-MM-DDTHH:MM:SS
archived_at: null        # 归档时设置
related_files:           # 关联文件（可选）
  - rpiv/requirements/prd-{name}.md
---
```

**状态流转**：`pending` → `in-progress` → `completed` → `archived`

每次修改过程文件内容时，必须同步更新 `status` 和 `updated_at`。

### 命名规范

- 功能名使用 kebab-case 格式
- 文件名前缀表示类型：`prd-`、`plan-`、`code-review-`、`exec-report-`、`system-review-`
- Todo 文件前缀表示子类型：`issue-`、`feature-`、`todo-`

## 命令全景图

### 核心流程命令

| 命令 | 阶段 | 用途 |
|------|------|------|
| `/rpiv_loop:brainstorm` | R 前 | 通过访谈对话澄清产品需求 |
| `/rpiv_loop:create-prd` | R | 基于对话上下文生成 PRD |
| `/rpiv_loop:plan-feature` | P | 深入代码库分析，创建实施计划 |
| `/rpiv_loop:execute` | I | 按计划逐步实施代码 |
| `/rpiv_loop:validation:code-review` | V | 代码审查，检查质量和安全 |
| `/rpiv_loop:validation:execution-report` | V | 生成实施报告，记录偏离 |
| `/rpiv_loop:validation:system-review` | V | 元级分析，对比计划与实施 |

### 辅助命令

| 命令 | 用途 |
|------|------|
| `/rpiv_loop:prime` | 加载项目上下文，建立代码库理解 |
| `/rpiv_loop:record` | 从对话中记录问题/需求/待办到 rpiv/todo |
| `/rpiv_loop:fix` | 基于 rpiv/todo 下的待办文件进行分析和修复 |
| `/rpiv_loop:flow-status` | 查看所有过程文件的状态 |
| `/rpiv_loop:archive` | 归档已完成的过程文件 |
| `/rpiv_loop:validation:code-review-fix` | 修复代码审查中发现的问题 |
| `/rpiv_loop:validation:validate` | 根据项目结构自动选择验证策略 |

### 自动化命令

| 命令 | 用途 |
|------|------|
| `/rpiv_loop:biubiubiu` | 一键启动全自主 agent 团队，自动完成 R→P→I→V |

## 阶段间信息流转

```
brainstorm 对话
      ↓
  create-prd  →  prd-{name}.md
      ↓                ↓
  plan-feature → plan-{name}.md  ← 读取 PRD + 代码库分析
      ↓                ↓
    execute    → 代码变更          ← 严格按计划实施
      ↓                ↓
  code-review  → code-review-{name}.md  ← 审查代码变更
      ↓
  exec-report  → exec-report-{name}.md  ← 记录实施与计划的偏离
      ↓
  system-review → system-review-{name}.md ← 元级分析，反馈到流程改进
```

**关键原则**：
- 计划阶段**不写代码**，只做分析和规划
- 实施阶段**严格按计划执行**，偏离需记录原因
- 验证阶段对比**计划 vs 实施**，发现流程改进机会

## Todo 系统

Todo 系统支持三种类型的待办条目，存放在 `rpiv/todo/`：

| 类型 | 适用场景 | 后续操作 |
|------|---------|---------|
| `issue` | 错误、bug、异常行为 | `/rpiv_loop:fix` 修复 |
| `feature` | 新功能需求 | `/rpiv_loop:brainstorm` 或 `/rpiv_loop:create-prd` |
| `todo` | 调研、配置、清理等一次性任务 | `/rpiv_loop:fix` 直接执行 |

Todo 文件使用独立的 frontmatter 结构（含 `title`、`type`、`priority` 字段），与过程文件的 frontmatter 略有不同。

## 验证三件套

验证阶段包含三个互补的检查维度：

| 检查 | 关注点 | 输出 |
|------|--------|------|
| **code-review** | 代码质量：逻辑错误、安全漏洞、性能问题 | `code-review-{name}.md` |
| **execution-report** | 实施记录：完成了什么、偏离了什么、为什么 | `exec-report-{name}.md` |
| **system-review** | 流程改进：偏离模式、根因分析、CLAUDE.md/命令更新建议 | `system-review-{name}.md` |

**执行顺序**：code-review → execution-report → system-review

system-review 是元级分析，它读取计划、执行报告和代码审查，分析流程本身的问题，产出可操作的改进建议。

## 典型工作流

### 标准流程（人工参与）

```
/rpiv_loop:brainstorm → /rpiv_loop:create-prd → /rpiv_loop:plan-feature → /rpiv_loop:execute → /rpiv_loop:validation:code-review → /rpiv_loop:validation:execution-report → /rpiv_loop:validation:system-review → /rpiv_loop:archive
```

每个阶段之间建议 `/clear` 清理上下文。

### 快速流程（小功能）

```
/rpiv_loop:create-prd → /rpiv_loop:plan-feature → /rpiv_loop:execute → /rpiv_loop:validation:code-review
```

### 全自动流程

```
/rpiv_loop:brainstorm → /rpiv_loop:biubiubiu
```

biubiubiu 会启动 agent 团队自动完成 PRD → Plan → Execute → Validate 全流程。
