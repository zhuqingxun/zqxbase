---
name: mint:extract
description: >-
  MINT 流水线 Stage 4: 结构化信息提取——从逐字稿中提取要点摘要、发言人分析（含深度意图分析）、行动项、关键决策等结构化产出物。支持选择输入源（clean 或 polished 稿）和指定产出物子集。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
version: 2.1.5
---


# mint:extract — 结构化信息提取

> **`{MINT_REF}` 路径约定**：指 mint 插件的 `references/` 目录，`{MINT_SCRIPTS}` 为同级 `scripts/` 目录。首次引用时通过
> `Glob("**/plugins/mint/references/lessons-learned.md")` 定位，多结果时优先非 `marketplaces/` 路径（私有开发版）。

从逐字稿中提取结构化信息，产出四种文档。

## 用法

```
/mint:extract <工作目录> [--source clean|polished] [--artifacts summary,speakers,actions,decisions]
```

示例：
- `/mint:extract D:\WORK\访谈记录\张三访谈`
- `/mint:extract D:\WORK\会议记录\产品评审会 --source polished`
- `/mint:extract D:\WORK\会议记录\周会 --artifacts summary,actions`

参数说明：
- `<工作目录>`：包含 meta.yaml 的 MINT 工作目录
- `--source`：输入源，默认 `clean`。`clean` 读取 `03_校对稿/{name}_校对稿.md`，`polished` 读取 `04_编辑稿/{name}_编辑稿.md`。当由 `/mint` 编排器调用时，如果 `04_编辑稿/` 目录存在内容，编排器会自动传递 `--source polished`
- `--artifacts`：指定生成哪些产出物，逗号分隔。默认全部生成。可选值：`summary`、`speakers`、`actions`、`decisions`

**关于脱敏**：extract 不提供独立的 `--脱敏` 参数。如果输入源是脱敏版本（如 `{name}_校对稿_脱敏.md`），产出物自然继承脱敏状态。

## 前置条件

1. 工作目录中存在 `meta.yaml`
2. 选定的输入源文件存在
3. 如果输入源不存在，提示用户先执行对应的前置阶段
4. 如果选定的输入源目录下存在脱敏版本文件（`*_脱敏.md`），通过 AskUserQuestion 询问用户是否使用脱敏稿作为输入。选项："使用原版" / "使用脱敏版"

## 四种产出物

### 1. 要点摘要（summary）

**文件**: `05_分析稿/要点摘要.md`

Executive Summary，1-2 页的精炼摘要，让读者快速了解全貌。

详细生成指引见 `{MINT_REF}/summary-prompt.md`。

### 2. 发言人分析（speakers）

**文件**: `05_分析稿/发言人分析.md`

每位发言人的观点提炼 + 深度意图分析。不只是"说了什么"，更要分析"为什么这么说"。

详细生成指引见 `{MINT_REF}/speaker-analysis-prompt.md`。

### 3. 行动项（actions）

**文件**: `05_分析稿/行动项.md`

从对话中提取的任务、承诺和后续跟进事项。

### 4. 关键决策（decisions）

**文件**: `05_分析稿/决策与遗留.md`

会议/访谈中达成的决策、共识，以及悬而未决的遗留问题。

## 执行流程

### 第一步：验证环境

1. 读取 `meta.yaml`，确认工作目录有效
2. 根据 `--source` 确认输入文件存在
3. 解析 `--artifacts` 确定需要生成的产出物列表

### 第二步：读取输入

读取指定的输入源文件全文。从 meta.yaml 获取项目上下文信息。

### 第三步：生成产出物

按以下顺序生成（有依赖关系，summary 最后生成效果更好）：

#### 3a. 发言人分析（speakers）

使用 `{MINT_REF}/speaker-analysis-prompt.md` 中的详细指引，分析每位发言人的：
- 显性立场和核心观点
- 隐性意图和策略行为
- 利益诉求和关切点
- 与其他发言人的互动关系

#### 3b. 行动项（actions）

从对话中提取明确或隐含的行动项，输出格式：

```markdown
# 行动项

> 来源：{输入文件名}
> 提取时间：{日期}

## 明确承诺的行动项

| # | 行动项 | 负责人 | 截止时间 | 依据原文 |
|---|--------|--------|----------|----------|
| 1 | {具体任务描述} | {谁承诺/被指派} | {提到的时间或"未明确"} | "{原话摘录}" |

## 隐含的后续跟进

以下内容虽未明确指派，但从讨论中可推断需要跟进：

| # | 建议行动 | 建议负责方 | 推断依据 |
|---|----------|------------|----------|
| 1 | {建议的跟进事项} | {最合适的负责方} | {为什么需要跟进} |
```

提取规则：
- 仅提取对话中**明确提及**的行动项（"我来做""你跟进一下""下周前完成"）
- "隐含的后续跟进"仅针对讨论中明显需要但未指派的事项
- 不要凭空创造行动项
- 截止时间如果是相对日期（"下周""月底"），根据 meta.yaml 的日期转换为绝对日期

#### 3c. 关键决策（decisions）

从对话中提取已达成的决策和未解决的问题：

```markdown
# 关键决策与遗留问题

> 来源：{输入文件名}
> 提取时间：{日期}

## 已达成的决策

### 决策 1：{决策标题}
- **决策内容**：{具体决定了什么}
- **决策背景**：{为什么做这个决定，1-2 句}
- **影响范围**：{这个决策影响哪些人/事}
- **依据原文**："{支撑这个决策的原话}"

### 决策 2：...

## 达成的共识

{虽然不是正式决策，但多方达成一致的观点}

1. **{共识主题}**：{共识内容}
   - 支持方：{哪些发言人表示同意}

## 遗留问题

{讨论中提出但未解决的问题}

| # | 问题 | 涉及方 | 阻塞原因 | 建议下一步 |
|---|------|--------|----------|------------|
| 1 | {问题描述} | {谁提出/谁需要回答} | {为什么未解决} | {建议如何推进} |
```

#### 3d. 要点摘要（summary）

最后生成摘要，因为可以参考前面已生成的 speakers/actions/decisions 内容提高质量。

使用 `{MINT_REF}/summary-prompt.md` 中的详细指引。

### 第四步：版本管理与输出

1. 如果 `05_分析稿/` 中已有同名文件，将旧版移动到 `05_分析稿/old/{filename}_v{N}.md`
2. 写入产出文件到 `05_分析稿/` 目录

### 第五步：更新 meta.yaml

```yaml
stages:
  extract:
    status: completed
    version: 1  # 或递增
    source: "clean"  # 或 "polished"
    completed_at: {当前 ISO 时间}
    params:
      model: "{使用的 LLM 模型}"
      artifacts: ["summary", "speakers", "actions", "decisions"]
      intent_depth: "deep"
      desensitized: false    # 是否基于脱敏输入
```

### 第六步：报告结果

报告每个产出文件的路径和关键统计：
- summary：字数
- speakers：分析了几位发言人
- actions：提取了几条行动项
- decisions：提取了几个决策 + 几个遗留问题

同时更新 `current`：
- `current.cursor` = `"extract"`
- `current.last_action_desc` = `"完成结构化提取"`

在 `stages.extract` 中写入 `produced` 字段（本次生成的 artifacts 列表），供 mint:next 的 Rule 3 判断交付物是否对齐。

### 最后一步：更新元数据并输出引导块

1. **刷新 current.last_action + 计算 next_hints**：
   ```bash
   uv run --script {MINT_SCRIPTS}/meta_io.py refresh-last-action "<工作目录>"
   uv run --script {MINT_SCRIPTS}/meta_io.py compute-next-hints "<工作目录>"
   ```

2. **渲染引导块**：
   - Read `{MINT_REF}/next-hints-template.md`
   - 用 compute-next-hints 输出的 JSON 填充 `{primary_cmd}` / `{primary_reason}` / `{alternatives_block}`
   - `{alternatives_block}` 按每行 `- {cmd}: {when}` 循环展开，空数组输出单行 `- 无`
   - 原样输出填充后的模板（保留开头的 `---` 分隔线）

## 质量控制

### 全局原则
- 所有产出物必须**有据可查**——每个观点、决策、行动项都能追溯到原文
- 不添加原文中没有的信息
- 区分"发言人明确表达的"和"分析推断的"，后者必须标注"推断"

### 各产出物自检
- **summary**：是否覆盖了最重要的话题？是否遗漏了关键决策或重大分歧？
- **speakers**：意图分析是否有原文证据支撑？是否过度解读？
- **actions**：是否把讨论中的建议误标为已承诺的行动项？
- **decisions**：是否把个人意见误标为集体决策？共识的支持方是否标注准确？

## 异常处理

| 情况 | 处理 |
|------|------|
| 输入源文件不存在 | 提示先执行对应的前置阶段 |
| 输入内容为空 | 报错退出 |
| 仅单人发言（如演讲） | speakers 仅分析该发言人，actions/decisions 可能为空 |
| 非会议类内容（如访谈） | actions 侧重"建议跟进"而非"已指派任务"，decisions 侧重"共识"而非"正式决策" |
| LLM 调用失败 | 报告错误，已完成的产出物保留 |
