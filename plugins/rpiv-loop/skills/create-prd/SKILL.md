---
name: rpiv-loop:create-prd
description: 基于对话上下文创建产品需求文档
argument-hint: "[功能主题]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 2.1.8
---

# Create PRD: 生成产品需求文档

## 前置初始化

首次执行前调用（幂等，已存在则静默跳过）：

```bash
uv run D:/CODE/plugins/rpiv-loop/tools/ensure_project_dod.py
```

该脚本若发现 `rpiv/dod.yaml` 缺失则从 `tools/dod_template.yaml` 拷贝初始化；已存在则静默跳过。确保项目级 DoD 通用门在后续 RPIV 各阶段可用。

## 概述

1. 基于以下输入生成全面的产品需求文档（PRD）。
    - 当前对话上下文和讨论的需求
    - $ARGUMENTS
2. 使用下面定义的结构和章节创建完整、专业的 PRD。
3. 针对输出文档架构中需要，但是未获取的内容，采用面试对话的形式和我互动，确保每一个关键细节都得到充分澄清。

## 输出文件

将 PRD 写入：`rpiv/requirements/prd-{kebab-case-feature-name}.md`

- 如果 `rpiv/requirements/` 目录不存在则创建
- `{kebab-case-feature-name}` 从用户输入或对话上下文中提取功能名称
- 示例：`prd-meeting-analysis.md`、`prd-user-auth.md`
- 每次执行都创建新文件，不覆盖已有的 PRD

### 文件格式

文件必须包含 YAML frontmatter 和内容：

```markdown
---
description: "产品需求文档: {feature-name}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
---

# {PRD 内容}
```

**Frontmatter 字段说明：**
- `description`: 文件描述
- `status`: 文件状态，新创建时固定为 `pending`
- `created_at`: 创建时间戳，ISO 8601 格式
- `updated_at`: 更新时间戳，创建时与 created_at 相同
- `archived_at`: 归档时间戳，创建时固定为 `null`

## PRD 结构

根据以下结构创建一个结构合理的产品需求文档（PRD）。根据现有信息调整各部分的深度和细节。

### 必需章节

**1. 执行摘要**
- 简洁的产品概述（2-3 段）
- 核心价值主张
- MVP 目标声明

**2. 使命**
- 产品使命声明
- 核心原则（3-5 个关键原则）

**3. 目标用户**
- 主要用户角色
- 技术舒适度
- 关键用户需求和痛点

**4. MVP 范围**
- **范围内：** MVP 的核心功能（使用 ✅ 复选框）
- **范围外：** 推迟到未来阶段的功能（使用 ❌ 复选框）
- 按类别分组（核心功能、技术、集成、部署）

**5. 用户故事**
- 主要用户故事（5-8 个故事），格式："作为 [用户]，我想要 [行动]，以便 [收益]"
- 为每个故事包含具体示例
- 如果相关，添加技术用户故事

**6. 核心架构与模式**
- 高级架构方法
- 目录结构（如果适用）
- 关键设计模式和原则
- 特定技术的模式

**7. 工具/功能**
- 详细的功能规范
- 如果构建代理：工具设计，包括目的、操作和关键功能
- 如果构建应用：核心功能分解

**8. 技术栈**
- 后端/前端技术及版本
- 依赖项和库
- 可选依赖项
- 第三方集成

**9. 安全与配置**
- 身份验证/授权方法
- 配置管理（环境变量、设置）
- 安全范围（范围内和范围外）
- 部署考虑

**10. API 规范**（如果适用）
- 端点定义
- 请求/响应格式
- 身份验证要求
- 示例负载

**11. 成功标准**
- MVP 成功定义
- 功能要求（使用 ✅ 复选框）
- 质量指标
- 用户体验目标

**12. 实施阶段**
- 分解为 3-4 个阶段
- 每个阶段包括：目标、交付物（✅ 复选框）、验证标准
- 现实的时间线估计

**13. 未来考虑**
- MVP 后的增强
- 集成机会
- 后期阶段的高级功能

**14. 风险与缓解措施**
- 3-5 个关键风险及具体的缓解策略

**15. 附录**（如果适用）
- 相关文档
- 关键依赖项及链接
- 仓库/项目结构

## 指令

### 1. 提取需求
- 审查整个对话历史
- 识别明确的需求和隐含的需求
- 注意技术约束和偏好
- 捕获用户目标和成功标准

### 2. 综合信息
- 将需求组织到适当的章节
- 在缺少细节的地方填入合理的假设
- 保持各章节的一致性
- 确保技术可行性

### 3. 编写 PRD
- 使用清晰、专业的语言
- 包含具体示例和细节
- 使用 Markdown 格式（标题、列表、代码块、复选框）
- 在技术章节中添加代码片段（如有帮助）
- 保持执行摘要简洁但全面

### 4. 质量检查
- ✅ 所有必需章节都存在
- ✅ 用户故事有明确的收益
- ✅ MVP 范围现实且定义明确
- ✅ 技术选择有理由
- ✅ 实施阶段可操作
- ✅ 成功标准可衡量
- ✅ 整个文档术语一致

## 样式指南

- **语调：** 专业、清晰、面向行动
- **格式：** 广泛使用 Markdown（标题、列表、代码块、表格）
- **复选框：** 使用 ✅ 表示范围内项目，❌ 表示范围外项目
- **具体性：** 优先使用具体示例而非抽象描述
- **长度：** 全面但可扫描（通常 30-60 个章节的内容）

## 前置检查

**在开始编写 PRD 之前：**

1. **版本替代检查**：检查 `rpiv/requirements/` 下是否存在同名特性的旧版本 PRD（如当前要创建 `prd-{name}-v2.md`，而 `prd-{name}.md` 已存在）。如果存在旧版本且状态不是 `superseded` 或 `archived`：
   - 使用 AskUserQuestion 询问用户是否将旧版本标记为 `superseded`
   - 如果确认，更新旧文件 frontmatter：`status: superseded`，追加 `superseded_by: rpiv/requirements/prd-{new-name}.md`，更新 `updated_at`

2. **识别 brainstorm-summary 来源**：检查对话上下文中是否引用了 `rpiv/brainstorm-summary-*.md` 文件。如果有，记录其路径，用于 PRD 完成后回写状态。

3. **识别 todo 来源**：如果用户通过 `--from-todo <path>` 参数指定了来源 todo 文件，或对话上下文中明确引用了 `rpiv/todo/feature-*.md` 文件，记录其路径，用于 PRD 完成后回写状态。

## 输出确认

创建 PRD 后：
1. 确认写入的文件路径
2. 提供 PRD 内容的简要摘要
3. 突出显示由于缺少信息而做出的任何假设
4. **更新上游文件状态**：
   - 如果在前置检查中识别到 brainstorm-summary 来源文件，将其 status 更新为 `completed`，更新 `updated_at`
   - 如果识别到 todo 来源文件，将其 status 更新为 `completed`，更新 `updated_at`，并在 todo 文件末尾追加 `promoted_to: rpiv/requirements/prd-{feature-name}.md`
5. 建议后续步骤：
   - "PRD 已生成。下一步建议：`/clear` 后执行 `/rpiv-loop:plan-feature {feature-name}` 创建实施计划。"

## 备注

- 如果缺少关键信息，在生成之前询问澄清问题
- 根据可用细节调整章节深度
- 对于高度技术性的产品，强调架构和技术栈
- 对于面向用户的产品，强调用户故事和体验
- 此命令包含完整的 PRD 模板结构 - 不需要外部引用
