---
name: rpiv-loop:biubiubiu
description: >-
  一键启动全自主 agent 团队，自动完成从 PRD 到验证的完整 RPIV 开发流程。brainstorm 完成后使用此命令，无需人工介入。当用户提到"自动开发"、"团队开发"、"全自主"、"biubiubiu"时触发。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion, TeamCreate, TaskCreate, TaskUpdate, SendMessage, Skill
version: 2.1.4
---

# Biubiubiu: 全自主 RPIV 团队执行

> **`{RPIV_SKILLS}` 路径约定**：指 rpiv-loop 插件的 `skills/` 目录。首次引用时通过
> `Glob("**/plugins/rpiv-loop/skills/biubiubiu/SKILL.md")` 定位，多结果时优先非 `marketplaces/` 路径（私有开发版）。

从对话上下文中提取需求，启动 agent 团队自主完成完整 RPIV 开发流程（PRD → Plan → Execute → Validate），全程无需用户介入。

## 团队架构

| 角色 | 职责 | 活跃阶段 |
|------|------|----------|
| **Leader**（你自己） | 协调、任务分配、阶段门禁、决策 | 全程 |
| **Architect** | PRD + Plan + 实现对齐审查 | 阶段 1-2, 4 |
| **Research** | 技术可行性调研（临时） | 阶段 1-2 |
| **QA** | 测试策略/用例/执行 + 代码审查 | 全程 |
| **Dev-1 / Dev-2** | 代码实现 | 阶段 3-4 |

## 执行流程

### 步骤 1：提取需求上下文

确定功能名称（从 `$ARGUMENTS` 或对话推断，kebab-case 格式）。

**如果 `$ARGUMENTS` 是已存在的文件路径**（PRD 或需求文档），直接使用该文件作为需求输入，跳到步骤 2。

**否则**，从对话上下文和 `$ARGUMENTS` 提取需求，保存到 `rpiv/brainstorm-summary-{feature-name}.md`：

```markdown
---
description: "需求摘要: {feature-name}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
---

# 需求摘要：{feature-name}

## 产品愿景
- 核心问题：...
- 价值主张：...
- 目标用户：...
- 产品形态：...

## 核心场景（按优先级）
1. ...

## 产品边界
- MVP 范围内：...
- 明确不做：...

## 约束条件
- ...

## 各场景功能要点
### 场景 1：...
```

### 步骤 2：创建团队

```
TeamCreate:
  team_name: rpiv-{feature-name}
  description: RPIV 全自主开发: {feature-name}
```

### 步骤 3：创建任务结构

使用 TaskCreate 创建以下任务，通过 TaskUpdate 设置 blockedBy 依赖：

```
阶段 1：需求与调研
  T1 create-prd        → Architect 基于需求摘要创建 PRD
  T2 tech-research     → Research 关键技术可行性调研
  T3 test-strategy     → QA 制定测试策略

阶段 2：架构规划
  T4 create-plan       → Architect 创建实施计划    [blockedBy: T1, T2]
  T5 test-specs        → QA 编写测试规格          [blockedBy: T1]

阶段 3：实现
  T6 implement         → Dev 代码实现             [blockedBy: T4]
  T7 write-tests       → QA 编写测试代码          [blockedBy: T4, T5]

阶段 4：验证
  T8 run-tests         → QA 运行测试              [blockedBy: T6, T7]
  T9 code-review       → QA 代码审查              [blockedBy: T6]
  T10 plan-alignment   → Architect 实现对齐审查    [blockedBy: T6]
  T11 delivery-report  → Leader 生成交付报告       [blockedBy: T8, T9, T10]
```

### 步骤 4：启动团队

**第一批（并行启动 3 个 agent）：**

使用 Task 工具启动以下 agent，设置 `team_name` 为当前团队名，`subagent_type` 为 `general-purpose`：

#### Architect Agent

名称：`architect`

提示词要点：
- 你是 RPIV 团队的架构师，负责产品设计和技术架构
- **首要步骤**：开始任何文档编写前，先读取项目 CLAUDE.md 获取部署平台、技术栈、架构等基础设施信息。PRD/Plan 中涉及部署、环境、技术栈的内容必须以 CLAUDE.md 为准，禁止自行推断
- **阶段 1**：读取需求摘要文件 `{brainstorm-summary-path}`，将其 `status` 更新为 `in-progress`。按照 RPIV create-prd 规范创建 PRD → `rpiv/requirements/prd-{feature-name}.md`。PRD 创建完成后，将需求摘要的 `status` 更新为 `completed`。PRD 规范参考读取 `{RPIV_SKILLS}/create-prd/SKILL.md`
- **阶段 2**：等待 tech-research 任务完成（通过 TaskList 检查），然后按照 RPIV plan-feature 规范创建实施计划 → `rpiv/plans/plan-{feature-name}.md`。计划规范参考读取 `{RPIV_SKILLS}/plan-feature/SKILL.md`。代码库分析要做充分，计划要足够详细，让 Dev agent 无需额外调研就能实现
- **阶段 4**：对比实现代码与计划，检查是否有偏离或遗漏，将审查结果通过 SendMessage 发给 team leader
- **完成任务的固定顺序**：标记 TaskUpdate completed 之前，必须先 Edit 对应的 `rpiv/` 文件，将 frontmatter `status` 更新为 `completed`、`updated_at` 更新为当前时间戳。顺序：Edit frontmatter → TaskUpdate completed，不可颠倒
- 完成每个任务后 TaskList 找下一个任务
- 遇到需要决策时自主决定，在文档中记录理由
- 全程使用中文

#### Research Agent

名称：`researcher`

提示词要点：
- 你是 RPIV 团队的技术调研员，负责关键技术的可行性分析
- 读取需求摘要 `{brainstorm-summary-path}`，识别关键技术点
- 调研内容：核心依赖库 API 兼容性和版本、框架特性支持（如 Streamlit）、性能约束、潜在技术风险
- **框架内置方案优先（硬性要求）**：对每个核心依赖库，必须检查是否有内置的抽象类/Provider/Handler 可直接使用。具体做法：读取依赖库源码中的 abstract class 和示例代码，而非仅搜索文档。调研结论必须明确回答"框架是否已提供此能力"，并附源码路径作为证据。只有在证明框架不支持后，才评估自研方案
- 调研结果保存到 `rpiv/research-{feature-name}.md`，文件必须包含 frontmatter：`status: pending`、`created_at`、`updated_at`
- 调研完成后，将 research 文件的 `status` 更新为 `completed`，更新 `updated_at`
- 通过 SendMessage 将关键发现告知 architect
- 你是临时角色，tech-research 任务完成后你的工作就结束了。标记任务完成，然后等待 shutdown
- 全程使用中文

#### QA Agent

名称：`qa`

提示词要点：
- 你是 RPIV 团队的质量保证工程师，贯穿全流程
- **阶段 1**：分析需求，制定测试策略文档 `rpiv/validation/test-strategy-{feature-name}.md`（frontmatter status: `pending`）
- **阶段 2**：基于 PRD 编写测试规格 `rpiv/validation/test-specs-{feature-name}.md`（frontmatter status: `pending`）和验收标准（等 PRD 完成后开始）
- **阶段 3**：基于实施计划编写测试用例代码（与 Dev 并行）
- **阶段 4**：运行测试 + 代码审查。测试全部通过后，将 test-strategy 和 test-specs 的 status 更新为 `completed`。代码审查规范参考读取 `{RPIV_SKILLS}/code-review/SKILL.md`。审查报告保存到 `rpiv/validation/code-review-{feature-name}.md`
- 审查标准要苛刻：安全问题标记为 CRITICAL，每个问题精确到文件和行号
- 如果发现 critical/high 问题，通过 SendMessage 立即告知 team leader
- **完成任务的固定顺序**：标记 TaskUpdate completed 之前，必须先 Edit 对应的 `rpiv/` 文件，将 frontmatter `status` 更新为 `completed`、`updated_at` 更新为当前时间戳。顺序：Edit frontmatter → TaskUpdate completed，不可颠倒
- 全程使用中文

**第二批（阶段 3 开始时启动）：**

当 create-plan 任务完成后（门禁 2 通过），根据 Plan 内容决定 Dev agent 数量：

判断标准：
- 任务可按模块明确分割（前后端、不同工具模块）且文件不重叠 → 2 个 Dev agent
- 任务主要顺序依赖或规模较小 → 1 个 Dev agent
- 确保 Dev agents 操作不同的文件集，避免冲突

#### Dev Agent

名称：`dev-1`（如有第二个则 `dev-2`）

提示词要点：
- 你是 RPIV 团队的开发工程师
- 读取实施计划 `rpiv/plans/plan-{feature-name}.md`
- 按照计划中的逐步任务实现代码。执行规范参考读取 `{RPIV_SKILLS}/execute/SKILL.md`
- 你负责的范围：{Leader 根据 Plan 指定的具体模块/文件列表}
- 严格按计划实现，不擅自扩展范围
- 遵循项目 CLAUDE.md 中的编码规范
- 每完成一个子任务运行基本语法验证
- 遇到计划不明确的地方，通过 SendMessage 询问 team leader
- **完成任务的固定顺序**：如果任务涉及 `rpiv/` 目录下的 .md 文件，标记 TaskUpdate completed 之前必须先 Edit 文件将 frontmatter `status` 更新为 `completed`、`updated_at` 更新为当前时间戳。顺序：Edit frontmatter → TaskUpdate completed，不可颠倒
- 全程使用中文

### 步骤 5：阶段协调

作为 Team Leader，你的核心工作是让并行最大化、阻塞最小化。

#### 门禁 1：PRD 就绪

Architect 完成 create-prd 后：
- 快速读取 PRD，检查是否覆盖需求摘要中的所有核心场景
- **Frontmatter 校验（grep 验证）**：用 `grep ^status:` 检查 PRD 文件和 brainstorm-summary 文件的 frontmatter status。如果 status 未更新为 `completed`，Leader 直接 Edit 修复（不要 SendMessage 要求 agent 补充，减少往返）
- 重大遗漏 → SendMessage 要求 Architect 补充
- 通过 → Architect 可进入 Plan 阶段

#### 门禁 2：Plan 就绪

Architect 完成 create-plan 后：
- 检查计划包含：上下文参考、逐步任务、测试策略、验证命令
- **Frontmatter 校验（grep 验证）**：用 `grep ^status:` 检查 Plan 文件和 research 文件的 frontmatter status。如果 status 未更新为 `completed`，Leader 直接 Edit 修复
- **框架方案检查**：确认计划中是否优先使用了框架内置能力（而非自研）。如果计划选择自研而调研报告未充分证明框架不支持，要求 Architect 补充论证
- 确定 Dev agent 数量和文件分工
- **多人协作检查**：如果项目有多个贡献者，先 `git fetch` 检查远程是否已有相关变更，避免重复实现
- 通过 → 启动 Dev agent(s)

#### 实现阶段：逐任务快速验证

在阶段 3 实现过程中，不要等所有实现完成后才审查。采用**滚动验证**模式：

- Dev 每完成一个子任务（Plan 中的一个 Task），通过 SendMessage 通知 Leader
- Leader 立即让 QA 对该子任务做**快速合规检查**（≤5 分钟）：语法验证、导入检查、与计划是否一致
- 快速检查发现 critical 问题 → 立即要求 Dev 修复再继续下一个任务
- 快速检查通过或仅有 low/medium 问题 → Dev 继续下一个任务，问题记录待最终审查处理

这确保了早期任务的错误不会传播到后续任务，同时不阻塞 Dev 的工作节奏。

#### 门禁 3：实现完成

所有子任务的快速检查通过后：
- QA 运行完整测试套件 + 全面代码审查
- Architect 做计划对齐审查
- 有 critical/high 问题 → SendMessage 要求 Dev 修复 → 重新测试（最多 3 轮）
- 全部通过 → 进入交付

#### 决策原则

遇到需要决策时，按以下优先级：
1. 项目 CLAUDE.md 中的规范
2. 需求摘要中的明确约束
3. 业界最佳实践
4. 最简方案（避免过度工程）

### 步骤 6：完成交付

所有验证通过后，**先输出以下 checklist，然后逐项执行并勾选**（防止中间步骤被团队关闭等交互流程冲断）：

```
交付 checklist：
- [ ] 6.1 生成交付报告
- [ ] 6.2 关闭团队
- [ ] 6.3 归档过程文件
- [ ] 6.4 向用户报告
```

1. **生成交付报告**保存到 `rpiv/validation/delivery-report-{feature-name}.md`：

```markdown
---
description: "交付报告: {feature-name}"
status: completed
created_at: {timestamp}
updated_at: {timestamp}
archived_at: null
related_files:
  - rpiv/requirements/prd-{feature-name}.md
  - rpiv/plans/plan-{feature-name}.md
  - rpiv/validation/code-review-{feature-name}.md
---

# 交付报告：{feature-name}

## 完成摘要
- PRD 文件：{路径}
- 实施计划：{路径}
- 代码变更：{创建/修改的文件列表}
- 测试覆盖：{测试用例数量和通过率}
- 代码审查：{问题数量和解决状态}

## 关键决策记录
{团队自主做出的重大决策及理由}

## 遗留问题
{未解决的问题和风险}

## 建议后续步骤
{推荐的改进和扩展方向}
```

2. **关闭团队**：对所有 agent 发送 `shutdown_request`，等待确认后 `TeamDelete`
3. **归档过程文件**：将本次流程产生的所有 `rpiv/` 过程文件归档到 `rpiv/archive/`。具体操作：
   - 创建 `rpiv/archive/` 目录（如不存在）
   - 遍历以下文件（如存在）：
     - `rpiv/todo/*{feature-name}*.md`
     - `rpiv/brainstorm-summary-{feature-name}.md`
     - `rpiv/research-{feature-name}.md`
     - `rpiv/requirements/prd-{feature-name}.md`
     - `rpiv/plans/plan-{feature-name}.md`
     - `rpiv/validation/test-strategy-{feature-name}.md`
     - `rpiv/validation/test-specs-{feature-name}.md`
     - `rpiv/validation/code-review-{feature-name}.md`
     - `rpiv/validation/delivery-report-{feature-name}.md`
   - 对每个文件：Edit frontmatter 将 `status` 改为 `archived`，添加 `archived_at` 时间戳，更新 `updated_at`
   - 移动文件到 `rpiv/archive/`（如有同名文件则加时间戳后缀）
   - 输出归档清单
4. **向用户报告**：输出交付物清单和关键信息摘要

## 异常处理

| 情况 | 处理 |
|------|------|
| agent 无响应 | 等待后重发消息。仍无响应则重新启动该 agent |
| 测试持续失败 | 最多 3 轮修复。超过后记录未解决问题，继续交付 |
| Research 发现致命阻断 | 暂停流程，在交付报告中记录阻断原因，向用户报告 |
| Dev agents 文件冲突 | 暂停冲突 agent，Leader 重新分配文件范围 |

## 规模自适应

根据项目规模调整团队配置：

- **小型**（预估 ≤3 文件变更）：3 agent — Leader + Architect(兼 Dev) + QA
- **中型**（4-10 文件）：4 agent — Leader + Architect + Dev-1 + QA
- **大型**（>10 文件或多模块）：5-6 agent — 完整团队配置

在步骤 1 完成后，根据需求复杂度判断规模，选择合适的团队配置。

## 备注

- 全程使用中文进行文档和沟通
- 所有产出文件遵循 RPIV 的 frontmatter 规范（status/created_at/updated_at/archived_at）
- agent 之间关键指令单独发送短消息，不要混在长文本中
- Research agent 是临时角色，Plan 完成后关闭以节省资源
- 如果项目已有 PRD 或 Plan，可跳过对应阶段，从现有文件继续
