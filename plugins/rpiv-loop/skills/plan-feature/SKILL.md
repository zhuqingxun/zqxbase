---
name: rpiv-loop:plan-feature
description: 通过深入的代码库分析和研究创建全面的功能计划
argument-hint: "<功能描述或 PRD 路径>"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion, WebSearch, WebFetch
version: 2.17.14
---

> `<rpiv-loop-root>` 解析顺序：环境变量 `RPIV_LOOP_ROOT` -> `CLAUDE_PLUGIN_ROOT` -> 当前插件根目录；均不存在时停止并请用户配置 `RPIV_LOOP_ROOT` 或 `CLAUDE_PLUGIN_ROOT`。

# 规划新任务

## 功能：$ARGUMENTS

## 使命

通过系统的代码库分析、外部研究和战略规划，将功能请求转换为**全面的实施计划**。

**核心原则**：在此阶段我们**不编写代码**。我们的目标是创建一个上下文丰富的实施计划，使 AI 代理能够一次性成功实施。

**关键理念**：上下文为王。计划必须包含实施所需的所有信息——模式、必读内容、文档、验证命令——以便执行代理在第一次尝试时就能成功。

## 规划流程

### 阶段 0：前置检查

**在开始规划前执行状态管理：**

1. 检查是否存在相关的 PRD 文件：`rpiv/requirements/prd-*.md`
2. 如果存在相关 PRD：
   - 读取该 PRD 文件内容
   - 检查是否有 YAML frontmatter
   - 根据 PRD 当前 status 处理：
     - `pending` → 更新为 `in-progress`，更新 `updated_at`
     - `in-progress` → **可能是上次会话中断**。提示用户但继续执行（Plan 创建完成后仍会将 PRD 标记为 completed）
     - `completed` → PRD 已完成，正常继续
     - `superseded` → 警告用户此 PRD 已被取代，询问是否仍要基于它创建 Plan
   - 记录 PRD 文件路径，用于后续 related_files
   - **读取 PRD frontmatter 的 `product_types` 字段**（缺失时按 `[code]` 处理，行为与改造前一致）。若含 `skill`，本次规划走 skill 分支：Read `<rpiv-loop-root>/references/skill-authoring/skill-plan-guide.md`，按其指引替换阶段 2 的调研内容、补充结构设计决策、并在阶段 5.6 注入 skill 标准 AC 条目。含 `code` 时下方各阶段原样执行；`[code, skill]` 时两者叠加、互不遮蔽
3. 如果没有 frontmatter（旧文件），跳过状态更新
4. **版本替代检查**：检查是否存在同名特性的旧版本文件（如当前要创建 `plan-{name}-v2.md`，而 `plan-{name}.md` 已存在；或新建的 `feature-{name}-complete.md` 取代旧 todo `todo-{name}-refine.md`）。如果存在旧版本且状态不是 `superseded` / `archived`，**按文件类型分别处理**：
   - **流程文件（PRD/Plan/validation 各类）**：使用 AskUserQuestion 询问用户是否将旧版本标记为 `superseded`。确认后更新旧文件 frontmatter：`status: superseded`，追加 `superseded_by: {新文件路径}`，更新 `updated_at`；同时建议在新文件反向加 `supersedes: {旧文件路径}` 形成双向闭环。
   - **todo 文件**：todo **不支持** `superseded`（hook 会拒）。使用 AskUserQuestion 询问用户是否将被取代的旧 todo **直接归档**：确认后更新旧文件 frontmatter `status: archived`，追加 `superseded_by: {新文件路径}` 作为追溯笔记，更新 `updated_at`。这与 flow_status 对误标 superseded 的 todo 的自动归一化产出一致——就地 `status: archived` 即逻辑终态；archive 技能只归档 `completed`/`superseded`，不会再搬已 `archived` 的文件，故 `archived_at` 可不补、物理位置不强制。

### 阶段 1：功能理解

**深入功能分析：**

- 提取要解决的核心问题
- 识别用户价值和业务影响
- 确定功能类型：新功能/增强/重构/错误修复
- 评估复杂度：低/中/高
- 映射受影响的系统和组件

**创建用户故事格式或完善用户提供的故事：**

```
作为 <用户类型>
我想要 <行动/目标>
以便 <收益/价值>
```

### 阶段 2：代码库情报收集

**使用专门的代理和并行分析：**

**1. 项目结构分析**

- 检测主要语言、框架和运行时版本
- 映射目录结构和架构模式
- 识别服务/组件边界和集成点
- 定位配置文件（pyproject.toml、package.json 等）
- 查找环境设置和构建流程

**2. 模式识别**（在有益时使用专门的子代理）

- 在代码库中搜索类似的实现
- 识别编码约定：
  - 命名模式（CamelCase、snake_case、kebab-case）
  - 文件组织和模块结构
  - 错误处理方法
  - 日志记录模式和标准
- 提取功能领域的常见模式
- 记录要避免的反模式
- 检查 CLAUDE.md 以了解项目特定的规则和约定

**3. 依赖分析**

- 编录与功能相关的外部库
- 了解库的集成方式（检查导入、配置）
- 在 docs/、ai_docs/、rpiv/reference 或 ai-wiki（如果可用）中查找相关文档
- 注意库版本和兼容性要求

**4. 测试模式**

- 识别测试框架和结构（pytest、jest 等）
- 查找类似的测试示例作为参考
- 了解测试组织（单元测试 vs 集成测试）
- 注意覆盖率要求和测试标准

**5. 集成点**

- 识别需要更新的现有文件
- 确定需要创建的新文件及其位置
- 映射路由器/API 注册模式
- 如果适用，了解数据库/模型模式
- 如果相关，识别身份验证/授权模式

**澄清模糊之处：**

- 如果此时需求不清楚，在继续之前询问用户以澄清
- 获取具体的实施偏好（库、方法、模式）
- 在继续之前解决架构决策

### 阶段 3：外部研究与文档

**在有益时使用专门的子代理进行外部研究：**

**文档收集：**

- 研究最新的库版本和最佳实践
- 查找带有特定章节锚点的官方文档
- 定位实施示例和教程
- 识别常见的陷阱和已知问题
- 检查破坏性更改和迁移指南

**技术趋势：**

- 研究技术栈的当前最佳实践
- 查找相关的博客文章、指南或案例研究
- 识别性能优化模式
- 记录安全考虑

**编译研究参考：**

```markdown
## 相关文档

- [库官方文档](https://example.com/docs#section)
  - 特定功能实施指南
  - 原因：需要 X 功能
- [框架指南](https://example.com/guide#integration)
  - 集成模式部分
  - 原因：展示如何连接组件
```

### 阶段 4：深度战略思考

**深入思考：**

- 此功能如何融入现有架构？
- 关键依赖和操作顺序是什么？
- 可能出现什么问题？（边缘情况、竞争条件、错误）
- 如何全面测试？
- 存在哪些性能影响？
- 是否有安全考虑？
- 这种方法的可维护性如何？

**设计决策：**

- 在替代方法之间选择，并给出明确的理由
- 为可扩展性和未来修改而设计
- 如果需要，规划向后兼容性
- 考虑可扩展性影响

### 阶段 5：计划结构生成

**使用以下结构创建全面的计划：**

完整计划模板已按 progressive disclosure 抽出：Read `<rpiv-loop-root>/references/plan-feature/plan-template.md`，按其结构逐节填写。

模板章节骨架（字段细节以模板文件为准）：功能描述 / 用户故事 / 问题陈述 / 解决方案陈述 / 功能元数据 / 上下文参考（必读文件・新建文件・相关文档・要遵循的模式）/ 实施计划（阶段 1-4）/ 逐步任务（DEPENDS_ON・IMPLEMENT・PATTERN・IMPORTS・GOTCHA・PROPAGATE・VALIDATE 字段）/ 测试策略 / 验证命令（级别 1-5）/ 验收标准 / 完成检查清单 / 备注

### 阶段 5.6：产出 acceptance.yaml（AC 对账的权威数据源）

**目的**：与 plan 文件同步生成结构化的 Gherkin 风格验收判据（AC），作为 `validate` 填写证据、`delivery-report` 门禁校验的唯一真实源。

**文件路径**：`rpiv/validation/<feature>/acceptance.yaml`（若目录不存在需一并创建）。

**plan 阶段职责**（本 SKILL 只写以下字段）：
- `id`：全文件唯一，格式 `AC-NNN`（三位数字），**禁止重复**
- `given` / `when` / `then`：严格按 Gherkin 三段式书写
- `verification_method`：具体到命令 / 测试文件路径 / 脚本名，禁止"人工检查"这种泛词
- `blocking`：`true` 表示强约束项，交付前必须 passed 或 not_applicable；`false` 为软性目标
- `notes`（可选）：额外上下文

**validate 阶段后续职责**（不要在 plan 阶段预填）：
- `evidence`：执行 verification_method 后的具体证据（路径:行号 / 日志片段 / 截图文件名）
- `status`：`passed` / `failed` / `not_applicable`（初始留空，由 QA 翻状态）

**delivery-report 阶段职责**：只读 `acceptance.yaml`，**禁止修改任何字段**。`check_acceptance.py` 通过 `uv run --no-project python <rpiv-loop-root>/tools/check_acceptance.py <feature>` 校验后以退出码决定能否出具交付报告。

**质量门（plan 阶段自检清单）**：
- [ ] `acceptance.yaml` 条目数 ≥ 3
- [ ] 所有 `id` 唯一且连号
- [ ] 所有 `verification_method` 非空且具体
- [ ] 每个 `blocking: true` 项都配了可执行的 `verification_method`
- [ ] `given/when/then` 用祈使句描述系统行为，禁止"用户应该感觉良好"这种无法验证的措辞

**YAML 示例**：Read `<rpiv-loop-root>/references/plan-feature/acceptance-template-example.md`（最小可用示例，复制后替换内容）；空白骨架另见 `<rpiv-loop-root>/tools/acceptance_template.yaml`，根键统一用 `criteria:`。

**产出约束**：
- 本章节要求 `acceptance.yaml` 与 plan.md **同一会话内产出**，缺一不可
- plan.md 的「验收标准」章节可保留对 plan 自身的 checklist，但强约束 AC 的**唯一权威源**是 `acceptance.yaml`
- 与 delivery-report 的 `check_acceptance.py` 构成闭环：plan 写骨架 → validate 翻状态 → delivery-report 校验通过才放行

---

## 输出格式

**文件名**：`rpiv/plans/plan-{kebab-case-feature-name}.md`

- 将 `{kebab-case-feature-name}` 替换为简短、描述性的功能名称
- 示例：`plan-user-authentication.md`、`plan-search-api.md`、`plan-database-refactor.md`

**目录**：如果不存在，创建 `rpiv/plans/`

### 文件格式

文件必须包含 YAML frontmatter 和内容：

```markdown
---
description: "功能实施计划: {feature-name}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
related_files:
  - rpiv/requirements/prd-{feature-name}.md  # 如果存在相关 PRD
---

# {计划内容}
```

**Frontmatter 字段说明：**
- `description`: 文件描述
- `status`: 文件状态，新创建时固定为 `pending`
- `created_at`: 创建时间戳，ISO 8601 格式
- `updated_at`: 更新时间戳，创建时与 created_at 相同
- `archived_at`: 归档时间戳，创建时固定为 `null`
- `related_files`: 关联文件列表（如果存在相关 PRD 则添加）

### 完成后续

计划创建完成后：

1. 如果在前置检查中更新了 PRD 的状态，将其 status 从 `in-progress` 改为 `completed`
2. 更新 PRD 的 `updated_at` 时间戳
3. 提示用户："计划已创建。相关 PRD 已标记为完成。"
4. 建议下一步："建议 `/clear` 后执行 `/rpiv-loop:execute rpiv/plans/plan-{feature-name}.md` 开始实施。"

## 质量标准

### 上下文完整性 ✓

- [ ] 所有必要的模式已识别和记录
- [ ] 外部库使用已记录并附有链接
- [ ] 集成点已清晰映射
- [ ] 已捕获陷阱和反模式
- [ ] 每个任务都有可执行的验证命令

### 实施就绪 ✓

- [ ] 其他开发者可以在没有额外上下文的情况下执行
- [ ] 任务按依赖顺序排列（可以从上到下执行）
- [ ] 每个任务都是原子的且可独立测试
- [ ] 模式引用包括特定的文件:行号

### 模式一致性 ✓

- [ ] 任务遵循现有代码库约定
- [ ] 新模式有明确的理由说明
- [ ] 没有重新发明现有的模式或工具
- [ ] 测试方法符合项目标准

### 信息密度 ✓

- [ ] 无通用引用（全部具体且可操作）
- [ ] URL 在适用时包含章节锚点
- [ ] 任务描述使用代码库关键字
- [ ] 验证命令是非交互式可执行的

## 成功指标

**一次性实施**：执行代理可以在没有额外研究或澄清的情况下完成功能

**验证完整**：每个任务至少有一个有效的验证命令

**上下文丰富**：计划通过"无先验知识测试" - 不熟悉代码库的人可以仅使用计划内容进行实施

**信心分数**：#/10 表示执行将在第一次尝试时成功

## 报告

创建计划后，提供：

- 功能和方法的摘要
- 创建的计划文件的完整路径
- 复杂度评估
- 关键实施风险或考虑因素
- 一次性成功的估计信心分数
