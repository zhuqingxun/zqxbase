---
name: rpiv-loop:record
description: 从对话上下文或用户描述中记录问题/需求/待办到 rpiv/todo
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
version: 2.1.2
---

# Record: 记录待办条目

将当前会话中发现的问题、功能需求或待办事项，结构化记录到 `rpiv/todo/` 目录下，形成可追踪的文件。支持三种类型：issue（问题/bug）、feature（功能需求）、todo（通用待办）。

## 输入

用户提供的描述或关键词：$ARGUMENTS

- 如果 $ARGUMENTS 不为空：以此为线索，结合对话上下文提取信息
- 如果 $ARGUMENTS 为空：扫描当前对话上下文，识别已讨论的问题/需求/待办，询问用户要记录哪一个

## 执行流程

### 阶段 1：信息提取与类型推断

1. **从对话上下文中提取**以下信息（尽可能多地自动识别）：
   - 标题（一句话概括）
   - 详细描述
   - 相关文件/模块
   - 参考链接（对话中提到的 URL、issue 链接等）

2. **自动推断类型**，基于以下信号：

   | 信号 | 推断类型 |
   |------|---------|
   | 错误信息、异常行为、"不工作"、"崩溃"、"报错"、回归问题 | `issue` |
   | "希望能..."、"增加...功能"、"支持..."、新 UI/交互、新接口 | `feature` |
   | 调研任务、配置变更、文档更新、迁移、清理、一次性操作 | `todo` |

3. 如果对话上下文中信息不足，且 $ARGUMENTS 提供了新的描述，则以 $ARGUMENTS 为主。

### 阶段 2：轻量确认

使用 AskUserQuestion 确认（最多 2 个问题）：

**必问**：
- 确认标题、推断的类型（展示提取结果，提供 issue/feature/todo 三个选项让用户确认或修改）

**可选**（仅当信息模糊时追问）：
- 优先级（high/medium/low）
- 是否有已知的 workaround 或补充信息

不要过度追问——文件后续可通过 `/rpiv-loop:fix` 或 `/rpiv-loop:create-prd` 流程补充。

### 阶段 3：生成文件

1. **确定文件名**：
   - 格式：`rpiv/todo/{type}-{kebab-case-name}.md`
   - 示例：`rpiv/todo/issue-dns-resolution-failure.md`、`rpiv/todo/feature-batch-export.md`、`rpiv/todo/todo-migrate-config.md`

2. **创建目录**（如果不存在）：
   ```bash
   mkdir -p rpiv/todo
   ```

3. **检查重名**：
   - 如果同名文件已存在，询问用户是追加/覆盖还是换名

4. **写入文件**，根据类型选择对应模板（见下方）

### 阶段 4：确认与引导

1. 展示生成的文件内容概要
2. 根据类型提示后续操作：

   | 类型 | 后续建议 |
   |------|---------|
   | `issue` | `/rpiv-loop:fix rpiv/todo/{name}.md` 立即修复 |
   | `feature` | `/rpiv-loop:brainstorm` 深入讨论，或 `/rpiv-loop:create-prd --from-todo rpiv/todo/{name}.md` 直接写 PRD |
   | `todo` | `/rpiv-loop:fix rpiv/todo/{name}.md` 直接执行 |

3. 通用提示：可通过 `/rpiv-loop:flow-status` 查看所有条目状态

## 文件模板

### 共享 Frontmatter

所有类型共享以下 frontmatter 结构：

```yaml
---
title: "{标题}"
type: issue | feature | todo
status: open
priority: medium
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
---
```

### Issue 模板（问题/bug）

```markdown
# {标题}

## 问题现象

{用户可感知的问题表现，包括错误信息、异常行为等}

## 根本原因

{如果已分析出原因则填写，否则写"待分析"}

## 影响范围

{受影响的功能、平台、版本等}

## 已知 Workaround

{如果有临时解决方案则填写，否则写"无"}

## 已尝试的方案

{在发现问题过程中已尝试但未解决的方案，帮助后续 /rpiv-loop:fix 避免重复尝试}

## 参考

{相关链接：GitHub issue、文档、日志截图路径等}
```

### Feature 模板（功能需求）

```markdown
# {标题}

## 动机与背景

{为什么需要这个功能，解决什么痛点}

## 期望行为

{功能的具体表现，用户视角的描述}

## 用户场景

{典型使用场景，1-3 个}

## MVP 定义

{最小可行版本应包含的核心能力}

## 备选方案

{如果有其他实现思路或替代方案则填写，否则写"无"}

## 参考

{相关链接、竞品参考、技术文档等}
```

### Todo 模板（通用待办）

```markdown
# {标题}

## 任务描述

{需要做什么，为什么要做}

## 涉及文件

{预计需要修改的文件或目录}

## 完成标准

{怎样算完成，验收条件}

## 备注

{补充信息、注意事项}
```

## 内容规范

1. **Issue**：问题现象应包含关键错误信息；根本原因未明确时标注"待分析"
2. **Feature**：MVP 定义要具体可执行，避免模糊的"支持 XXX"
3. **Todo**：完成标准必须可验证
4. 章节内容为空时写"无"而不是删除该章节，保持结构完整
5. 参考章节收录对话中出现的所有相关链接

## 特殊情况处理

1. **对话中有多个条目**：询问用户要记录哪一个，或是否全部记录（每个条目一个文件）
2. **条目已有对应文件**：提示用户已存在同名文件，询问是否更新现有文件
3. **上游/外部问题**（如第三方 bug）：类型为 issue，在"根本原因"中标注"上游问题"，在"参考"中记录外部 issue 链接
