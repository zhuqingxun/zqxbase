---
name: ppt:create
description: >-
  从目录或文件一键生成最高质量 PPT。支持 Markdown 输入和图片资产。
  当用户提到"生成 PPT""做 PPT""创建演示文稿""ppt:create"时触发。
  也适用于: 用户提供了 markdown 文件或目录并要求转化为 PPT 的场景。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
version: 3.0.1
---

# PPT:Create — 一键生成最高质量 PPT

从目录/文件输入，经过四阶段管线 + 审查门禁，生成高质量 .pptx 文件。

## 路径约定

本文档中 `<plugin-root>` 指 plugin 根目录。推导方式：Base directory 的两级父目录（即 `skills/create/` 的上两层）。执行 bash 命令前，先确定实际路径再替换 `<plugin-root>`。

## 核心原则

**质量优先** — 愿意用时间、token、人工介入换取高质量输出。

## 参数解析

从 `$ARGUMENTS` 中解析：
- **输入路径**（必需）：目录路径或文件路径
- `--preset <name>`：内容组织预设（默认 `research-report`），可选值见 `<plugin-root>/presets/`
- `--theme <name>`：视觉主题（默认 `clean-light`），可选值见 `<plugin-root>/themes/`
- `--output <path>`：输出路径（默认 `./output/<input-name>.pptx`）

## 执行流程

### Stage 1: Parse（多格式解析）

运行解析脚本：
```bash
uv run python <plugin-root>/engine/parse.py <input-path> --output <workdir>/parsed-content.json
```

解析完成后，**你作为审查 Agent-P** 审查 `parsed-content.json`：

**审查维度**（阈值 4.5/5，最多 10 轮）：
- **完整性**（5分）：对比输入目录文件列表，是否有遗漏文件？
- **结构识别准确率**（5分）：标题层级、列表、表格、代码块是否正确识别？
- **格式保真度**（5分）：内容块是否保留了原始格式信息？

输出审查 JSON：
```json
{
  "pass": true/false,
  "score": 4.5,
  "dimensions": {
    "completeness": {"score": 5, "evidence": "...", "issues": []},
    "structure_accuracy": {"score": 4, "evidence": "...", "issues": ["..."]},
    "format_fidelity": {"score": 5, "evidence": "...", "issues": []}
  },
  "threshold": 4.5,
  "improvement_directives": []
}
```

**强制举证规则**：每个评分必须引用具体文件名或内容块。扣分必须给出改进指令。满分必须论证为何无法进一步改进。

不通过时：将 `improvement_directives` 反馈给 parse.py 重新处理。连续 3 轮无提升 → 将反馈交给用户决策。第 10 轮 → 输出当前最佳版本。

### Stage 2: Architect（内容架构设计）

读取 `parsed-content.json`、预设文件和 `<plugin-root>/design-guide.md`（设计哲学和反模式清单）。

**你作为 AI 内容架构师**，执行以下任务：
1. 全局分析所有输入材料的核心信息
2. 提炼核心论点/叙事线
3. 做出内容取舍决策 — 哪些纳入、哪些裁剪
4. 设计叙事弧线（opening -> context -> evidence -> challenges -> recommendations -> closing）
5. 划分章节，每章明确核心信息和预计页数
6. **为每页规划结构化内容要点**（每 point 的 body 80-150 字，含数据/案例/论证细节）
7. **为每页撰写 description**（1-3 句上下文描述）
8. **标记数据来源为 footnote**

产出 `<workdir>/content-architecture.yaml`，格式：
```yaml
thesis: "核心论点（完整句子）"
target_audience: "目标受众"
arc: "opening -> context -> evidence -> ... -> closing"
chapters:
  - title: "章节名"
    key_message: "核心信息"
    source_refs: ["file.md:15-42"]
    slide_briefs:
      - slide_title: "行动标题（传达观点，不只是描述）"
        visual_type_hint: "data-contrast"
        description: "1-3 句上下文描述（必填）"
        content_points:
          - heading: "指标/卡片标题"
            body: "80-150字详细阐述，从源材料提取具体数据、案例或论证"
            metric_value: "大号指标值"
            metric_label: "指标标签"
          - heading: "第二个指标/卡片标题"
            body: "80-150字详细阐述"
            metric_value: "对比指标值"
            metric_label: "对比标签"
        footnote: "数据来源: xxx（有数据引用时必填）"
      - slide_title: "另一页行动标题"
        visual_type_hint: "cards-3"
        description: "1-3 句上下文"
        content_points:
          - heading: "卡片标题1"
            body: "80-150字详细阐述"
          - heading: "卡片标题2"
            body: "80-150字详细阐述"
          - heading: "卡片标题3"
            body: "80-150字详细阐述"
total_slides: 18
excluded_content:
  - reason: "裁剪原因"
    source_ref: "file.md:120-135"
    content_summary: "被裁剪的内容摘要"
```

**内容量硬约束**：
- 每个 `content_points` 的 `body` 字段必须 80-150 字
- cards/comparison/process 类型的 content_points **必须有 heading**
- data-contrast 类型 **必须有 metric_value + metric_label**
- 非豁免页面（hero-statement/quote-hero/story-card 除外）**必须有 description**
- 有数据引用的页面 **必须有 footnote**

写摘要性短句（body<40字）是最常见的质量问题根因——Stage 3 的 validate_plan.py 会拦截，但在此阶段就应保证充足。

产出后，**你切换为审查 Agent-A** 审查：

**审查维度**（阈值 4.0/5，最多 10 轮）：
- **叙事连贯**（5分）：叙事弧线是否有逻辑递进？
- **信息覆盖**（5分）：核心信息是否被充分覆盖？
- **受众匹配**（5分）：内容深度和表达方式是否匹配目标受众？
- **精炼度**（5分）：是否有冗余或重复？
- **结构均衡**（5分）：各章节页数分配是否合理？

审查通过后，**用户确认点**（必须使用 AskUserQuestion 工具）：

先输出架构摘要（核心论点、章节标题+核心信息、预计页数、被裁剪内容清单），然后用 AskUserQuestion 提供选项：

- **选项 1**："确认，进入 Stage 3 视觉规划"
- **选项 2**："需要调整"（用户输入修改意见后重新架构）
- **选项 3**："查看某章节的详细 content_points"（展示后再决策）

用户选择确认后进入下一阶段。

### Stage 3: Plan（视觉规划）

读取 `content-architecture.yaml`、主题 YAML、预设 YAML、`<plugin-root>/design-guide.md`。

**你作为 AI 视觉规划师**，为每页做视觉设计决策：

对每一页 slide：
1. 根据内容类型选择 visual type（使用下方决策框架）
2. 参考预设的 `visual_type_preferences` 权重
3. 指定设计参数（来自主题 YAML）
4. 确保全局视觉一致性
5. **key_points 必须使用结构化对象格式**（heading + body，data-contrast 加 metric_value + metric_label）
6. **每页必须有 description**（豁免类型除外）
7. **有数据的页面必须有 footnote**
8. **连续 2 页不得使用相同 visual_type**（布局多样性约束）

**Visual Type 决策框架**（按顺序匹配）：
1. 有序列/流程？ → `process-N-phase`（N=2-5）
2. 有对比？ → `comparison-N`（N=2-5）
3. 有并列但非序列的条目？ → `cards-N`（N=2-5）
4. 有两组数据的张力/对比？ → `data-contrast`
5. 有有力引言？ → `quote-hero`
6. 数据确实是表格形式？ → `table`
7. 单句核心陈述？ → `hero-statement`
8. 默认 → `bullets`

**禁止**：
- hero-statement 不得用于 3+ 条目的内容
- table 不得用于流程/方法论
- bullets 不得用于并列对比

产出 `<workdir>/slide-plan.yaml`（schema 由 `schemas/slide_plan.py` 定义）。

**内容量门禁**（强制，不可跳过）：

slide-plan.yaml 写入后，立即运行校验脚本：
```bash
uv run --script <plugin-root>/engine/validate_plan.py <workdir>/slide-plan.yaml --json
```

校验规则（按 visual type）：
- `cards-N` / `process-N-phase` / `framework*` / `timeline*`：每 key_point ≥ 80 字
- `comparison-N`：每 key_point ≥ 100 字
- `bullets`：key_points 总计 ≥ 200 字
- `data-contrast`：内容区总计 ≥ 80 字
- `table`：rows ≥ 2 且 headers 非空
- `hero-statement` / `quote-hero` / `story-card`：豁免

**校验不通过时**：
1. 读取 JSON 输出中 `status: "FAIL"` 的 slides 清单
2. 对每个 FAIL slide，根据 `point_issues` 或 `total_issue` 补充内容——从 `content-architecture.yaml` 的 source_refs 回溯源材料，提取具体数据、案例或论证细节
3. 更新 slide-plan.yaml 后重新运行校验
4. 连续 3 轮无法全部通过 → 将 FAIL 清单交给用户决策（AskUserQuestion：接受当前版本 / 手动补充内容 / 降低该 slide 的 visual type 复杂度）

产出后，**你切换为审查 Agent-V** 审查：

**审查维度**（阈值 4.0/5，最多 10 轮）：
- **visual type 适配度**（5分）：每页选择的 visual type 是否最佳匹配内容？
- **设计一致性**（5分）：配色/字号/间距是否全局一致？
- **主题规范符合度**（5分）：所有参数是否来自主题定义？
- **信息层级清晰度**（5分）：标题/正文/辅助信息的层级是否清晰？

### Stage 4: Render（确定性渲染）

运行渲染脚本：
```bash
uv run python <plugin-root>/engine/render.py <workdir>/slide-plan.yaml --theme <theme> --output <output-path>
```

渲染完成后，运行渲染后校验：
```bash
uv run --script <plugin-root>/engine/validate_plan.py <workdir>/slide-plan.yaml --json
```

如果校验仍有 FAIL（理论上 Stage 3 已通过，此处为防御性检查），**立即停止管线**，用 AskUserQuestion 报告问题。

然后，**你作为审查 Agent-R** 执行视觉 QA：

**QA 验证循环**（假设有问题，你的工作是找到它们）：

1. **内容 QA**：检查 validate_plan.py --json 的输出，关注 FAIL 和 WARN（包括反模式警告）
2. **渲染 QA**：检查 render.py 的退出码和 stderr 输出
3. **视觉 QA**（如有 LibreOffice）：
   ```bash
   soffice --headless --convert-to pdf <output-path>
   pdftoppm -jpeg -r 150 <output>.pdf slide
   ```
   转为图片后，用 Agent 子代理以全新视角审查：
   - 重叠元素（文本穿过形状、线条穿过文字）
   - 文本溢出或在边界处截断
   - 间距不均（一处大空白，另一处拥挤）
   - 低对比度文字
   - 留白过多的页面
4. **无 LibreOffice 时**：基于 slide-plan.yaml 推理检查字号对比度、布局多样性、内容密度
5. 发现问题 → 修改 slide-plan.yaml → 重渲染 → 再验证
6. **至少完成一轮"修复-验证"循环后才能声明完成**

**审查维度**（阈值 4.5/5，最多 10 轮）：
- **无溢出/截断**（5分）：所有文本是否在形状边界内？
- **字体覆盖率**（5分）：所有字符是否能被指定字体渲染？
- **图片比例**（5分）：图片是否保持原始宽高比？
- **视觉一致性**（5分）：配色/间距/字号是否与 slide-plan 一致？
- **可读性**（5分）：最小字号是否 >= 12pt？对比度是否足够？

**FAIL 时强制停管线**：审计不通过时，**禁止 LLM 自行决定如何处理**。必须用 AskUserQuestion 向用户展示 FAIL 详情，提供选项：
- "修复后重新渲染"（AI 修改 slide-plan.yaml 参数后重跑 render）
- "接受当前版本"（用户知情接受）
- "放弃本次生成"

### 完成

输出：
```
PPT 已生成: <output-path>
N 页 | 主题: <theme> | 预设: <preset>
如需调整，使用 /ppt:refine <output-path> <调整指令>
```

## 中间产物路径

所有中间产物存放在 `<output-dir>/.ppt-workdir/`：
- `parsed-content.json`
- `content-architecture.yaml`
- `slide-plan.yaml`

## 退化保护

- 连续 3 轮审查评分无提升 → 自动将审查反馈 + 当前产出交给用户决策
- 第 10 轮仍未通过 → 输出当前最佳版本 + 未解决问题清单
