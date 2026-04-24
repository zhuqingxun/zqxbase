---
name: rpiv-loop:delivery-report
description: >-
  生成功能交付报告，聚合所有 RPIV 工件为面向外部的交付摘要
allowed-tools: Read, Bash, Grep, Glob, Write
version: 2.1.7
---

# Delivery Report: 交付报告

聚合一个功能的所有 RPIV 过程工件，生成面向外部（团队成员、利益相关方）的交付摘要文档。

## 定位

- **exec-report** = 面向开发者的实施记录（做了什么、遇到什么问题）
- **system-review** = 面向流程的元分析（计划与实施的偏离、流程改进）
- **delivery-report** = 面向外部的交付摘要（交付了什么、质量如何、还有什么遗留）

## 用法

```bash
/rpiv-loop:delivery-report feature-name
```

## 第 0 步：AC gate 硬校验（必须最先执行）

**第一步必须调用** AC 对账脚本，未通过则立即中断，不得进入后续任何步骤：

```bash
uv run D:/CODE/plugins/rpiv-loop/tools/check_acceptance.py <feature>
```

（消费项目上下文中若插件根在 PATH 变量里，也可写为 `uv run <插件根>/tools/check_acceptance.py <feature>`。）

**退出码语义**：

| 退出码 | 含义 | 本 SKILL 动作 |
|--------|------|--------------|
| `0`    | 全部 blocking AC 均 passed 或 not_applicable，evidence 非空 | 继续进入步骤 1 |
| `1`    | 有 blocking AC 未通过（status 为空 / failed / evidence 缺失） | **立即 raise**，输出 failing AC 清单，**禁止生成交付报告** |
| `2`    | `acceptance.yaml` 缺失或 YAML 解析失败 | 要求先跑 plan-feature 补齐 acceptance.yaml，**禁止生成交付报告** |

**重要约束（流程纪律）**：
- 本 SKILL **只读** `rpiv/validation/<feature>/acceptance.yaml`
- **禁止在 delivery-report 阶段修改 acceptance.yaml 的任何字段**（包括 evidence / status），违反视为流程违规
- 如需修正 AC，回退到 `plan-feature`（修结构）或 `validate`（翻 status / 填 evidence），完成后再回到本 SKILL

**hook 兜底**：即使本 SKILL 文字被忽略，`hooks/block_unverified_delivery.py` 会在 Write `rpiv/validation/delivery-report-*.md` 时再跑一次 `check_acceptance.py`，退出码非 0 则 exit 2 + stderr 阻止 Claude Code 保存。3 层保险确保"美化式绕过"不可能发生。

---

## 前置条件

执行前自动检查以下文件是否存在且为 `completed`：

| 文件 | 必需 | 说明 |
|------|:----:|------|
| PRD | 是 | 需求基线 |
| Plan | 是 | 实施计划 |
| exec-report | 是 | 实施记录 |
| code-review | 推荐 | 不存在时警告但不阻断 |
| system-review | 推荐 | 不存在时警告但不阻断 |

如果必需文件缺失或非 completed 状态，提示用户先完成上游步骤，不生成报告。

## 执行流程

### 步骤 1：收集工件

自动发现 `$ARGUMENTS`（feature-name）关联的所有文件：

```
rpiv/brainstorm-summary-{feature-name}.md
rpiv/research-{feature-name}.md
rpiv/requirements/prd-{feature-name}.md
rpiv/plans/plan-{feature-name}.md
rpiv/validation/exec-report-{feature-name}.md
rpiv/validation/code-review-{feature-name}.md
rpiv/validation/system-review-{feature-name}.md
rpiv/todo/*-{feature-name}.md
```

读取每个存在的文件，提取关键信息。

### 步骤 2：提取代码变更

从 exec-report 中提取：
- 新增/修改的文件列表
- 变更行数
- 验证结果（测试通过率、lint 结果）

### 步骤 3：提取质量信息

从 code-review 中提取（如果存在）：
- 发现的问题数量和严重级别
- 已修复 vs 未修复的问题
- 整体质量评分

从 system-review 中提取（如果存在）：
- 计划对齐分数
- 关键偏离及原因

### 步骤 4：生成报告

保存到：`rpiv/validation/delivery-report-{feature-name}.md`

## 输出格式

```markdown
---
description: "交付报告: {feature-name}"
status: completed
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
related_files:
  - rpiv/requirements/prd-{feature-name}.md
  - rpiv/plans/plan-{feature-name}.md
  - rpiv/validation/exec-report-{feature-name}.md
  - rpiv/validation/code-review-{feature-name}.md      # 如果存在
  - rpiv/validation/system-review-{feature-name}.md    # 如果存在
---

# 交付报告：{feature-name}

## 功能概述

{从 PRD 执行摘要中提取的 2-3 句话概述}

## 交付物清单

### 过程文档

| 文档 | 路径 | 状态 |
|------|------|------|
| PRD | rpiv/requirements/prd-{name}.md | completed |
| Plan | rpiv/plans/plan-{name}.md | completed |
| Exec Report | rpiv/validation/exec-report-{name}.md | completed |
| Code Review | rpiv/validation/code-review-{name}.md | completed |
| System Review | rpiv/validation/system-review-{name}.md | completed |

### 代码变更

| 类型 | 文件 |
|------|------|
| 新增 | {文件列表，从 exec-report 提取} |
| 修改 | {文件列表} |

变更统计：+{新增行} -{删除行}

## 质量评估

### 测试结果

{从 exec-report 验证结果提取}

### 代码审查

- 发现问题：{总数}（Critical: {n}, High: {n}, Medium: {n}, Low: {n}）
- 已修复：{n}/{总数}
- 遗留：{列出未修复的问题，如果有}

### 计划对齐

- 对齐分数：{n}/10
- 偏离数量：{n}（合理: {n}, 有问题: {n}）

## 关键决策

{从 exec-report 的偏离记录和 system-review 中提取的重要决策，每条简述原因}

## 遗留问题

{从 code-review 未修复项 + system-review 改进建议中整理}

- [ ] {遗留问题 1}
- [ ] {遗留问题 2}

## 建议后续步骤

{从 system-review 和 exec-report 建议中整理}

1. {后续步骤 1}
2. {后续步骤 2}
```

## 完成后续

1. 报告创建时 status 即为 `completed`（与 exec-report 相同，属于事实记录）
2. 提示用户下一步操作：
   - "交付报告已生成。建议执行 `/rpiv-loop:archive {feature-name}` 归档所有已完成文件。"
3. 列出该功能的所有文件及当前状态，方便用户确认

## 注意事项

- 报告内容完全从已有工件中聚合，不进行新的代码分析
- 缺失的可选工件（code-review、system-review）在报告中标注"未执行"，对应章节简化为一行说明
- 保持报告简洁可扫描，每个章节不超过 10 行
- 全程使用中文
