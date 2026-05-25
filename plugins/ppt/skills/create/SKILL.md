---
name: ppt:create
description: >-
  从目录或文件一键生成最高质量 PPT。支持 Markdown 输入和图片资产。
  当用户提到"生成 PPT""做 PPT""创建演示文稿""ppt:create"时触发。
  也适用于: 用户提供了 markdown 文件或目录并要求转化为 PPT 的场景。
argument-hint: "<输入路径> [--preset <name>] [--theme <name>] [--output <path>]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
version: 3.0.4
---

# PPT:Create — 一键生成最高质量 PPT

## v3.4.0 简化说明

v3.3.x 把 4 个独立 LLM reviewer (Agent-P/A/V/R) 各跑 10 轮迭代 + 多重 4.x/5 评分门禁堆叠, 用户反思"skill 越做越复杂效果远没达到预期"——LLM 评分无 ground truth, 模糊上"过得去"的输出占据大半 token. v3.4.0 删除所有非 deterministic reviewer, 保留 deterministic 校验 (`validate_plan.py` 内容量 + 应用率门禁) + 1 个用户确认 gate, 视觉评审交给独立的 `/ppt:taste` skill (后置, 用户按需调用).

四阶段流水线保留 (parse → architect → plan → render), 但每阶段仅 deterministic 校验 + 失败 fail-fast, 不再做 LLM self-review.

## 路径约定

`<plugin-root>` 指 plugin 根目录, 推导: skills/create/ 的两级父目录. 执行 bash 前替换为实际绝对路径.

## 参数解析

从 `$ARGUMENTS` 中解析:
- **输入路径** (必需): 目录路径或文件路径
- `--preset <name>`: 内容预设 (默认 `research-report`), 可选值见 `<plugin-root>/presets/`
- `--theme <name>`: 视觉主题 (默认 `huawei`, v3.4.0 仅 huawei). 旧主题 (`clean-light` / `academic` / `dark-business`) 显式传入会 `ValueError`
- `--output <path>`: 输出路径 (默认 `./output/<input-name>.pptx`)

## 执行流程

### Stage 1: Parse (deterministic)

```bash
uv run python <plugin-root>/engine/parse.py <input-path> --output <workdir>/parsed-content.json
```

parse.py 失败 (exit ≠ 0) 立即停管线并报错给用户, 不做 LLM review.

### Stage 2: Architect (LLM 产出 + 用户确认 gate)

读取 `parsed-content.json`、预设文件 `<plugin-root>/presets/<preset>.yaml`、`<plugin-root>/design-guide.md`.

**你作为内容架构师**:
1. 全局分析输入材料的核心信息, 提炼核心论点 / 叙事线
2. 做内容取舍 (哪些纳入 / 裁剪), 划分章节, 设计叙事弧线
3. 为每页规划结构化内容要点 (每 point 的 body **80-150 字**, 含数据 / 案例 / 论证细节)
4. 为每页撰写 description (1-3 句上下文), 数据引用页标 footnote

产出 `<workdir>/content-architecture.yaml`:
```yaml
thesis: "核心论点 (完整句子)"
target_audience: "目标受众"
arc: "opening -> context -> evidence -> ... -> closing"
chapters:
  - title: "章节名"
    key_message: "核心信息"
    source_refs: ["file.md:15-42"]
    slide_briefs:
      - slide_title: "行动标题 (传达观点, 不只是描述)"
        visual_type_hint: "data-contrast"
        description: "1-3 句上下文 (必填, 豁免类型除外)"
        content_points:
          - heading: "卡片标题"
            body: "80-150 字详细阐述, 从源材料提取数据 / 案例 / 论证"
            metric_value: "大号指标值"
            metric_label: "指标标签"
        footnote: "数据来源 (有数据引用时必填)"
total_slides: 18
excluded_content:
  - reason: "裁剪原因"
    source_ref: "file.md:120-135"
    content_summary: "被裁剪的内容摘要"
```

**内容量硬约束** (Stage 3 的 validate_plan 会再次拦截, 此处先尽力保证):
- `content_points.body` 字段 80-150 字
- cards / comparison / process 类型 content_points **必须有 heading**
- data-contrast **必须有 metric_value + metric_label**
- 非豁免页面 (hero-statement / quote-hero / story-card 除外) **必须有 description**
- 有数据引用的页面 **必须有 footnote**

**用户确认 gate (必须 AskUserQuestion)**:

输出架构摘要 (核心论点、章节标题 + 核心信息、预计页数、被裁剪内容清单), 然后 AskUserQuestion:

- 选项 1: "确认, 进入视觉规划"
- 选项 2: "需要调整" (用户输入修改意见后重做 Architect)
- 选项 3: "查看某章节的详细 content_points"

用户确认后进入 Stage 3.

### Stage 3: Plan (LLM 产出 + deterministic 门禁)

读取 `content-architecture.yaml`、主题 yaml、preset yaml、`<plugin-root>/design-guide.md`、`<plugin-root>/anchors.yaml` (huawei 审美锚点 metadata, 不默认 Read PNG).

锚点库使用: `anchors.yaml.usage_by_skill.ppt:create` — 决定 layout 时查 layout_only / extended 找参考案例 (学 layout 不学 palette, 按原则 P2); 生成前对照 antipatterns AP1-AP5 主动避免反模式.

**前置: 装载主题决策框架**:
```bash
uv run --script <plugin-root>/engine/prompt_assembler.py --theme <theme> --output <workdir>/.theme-prompt.md
```

Read `.theme-prompt.md` — 由 `engine/prompt_assembler.py` 从 `themes/<theme>/preferences.yaml` + `schemas/variants.py` 派生, 含 6 类硬约束 + 12 类软引导 + 18 版式字段速查 + 退回链 + path X 字段填法.

**所有视觉规划决策必须严格遵循 `.theme-prompt.md`**.

**你作为视觉规划师**, 为每页:
1. 按 .theme-prompt.md 硬约束 + 软引导选 visual_type (通用 fallback 决策树见下)
2. key_points 用结构化对象格式 (heading + body, data-contrast 加 metric_value + metric_label)
3. 每页有 description (豁免类型除外), 数据页有 footnote
4. 连续 2 页不得用相同 visual_type (布局多样性)

**huawei 18 版式字段填法**:
- 公共字段 (title / subtitle / description) → `slide.content`
- 专属字段 (kpis / chapters / layers / steps / phases / quadrants / personas / risks / units / ...) → `slide.variant`
- 不要把专属字段平铺到 slide.content 顶层

**通用 Visual Type 决策树** (仅 .theme-prompt.md 加载失败时):
1. 有序列 / 流程 → `process-N-phase` (N=2-5)
2. 有对比 → `comparison-N` (N=2-5)
3. 有并列非序列条目 → `cards-N` (N=2-6)
4. 两组数据张力 → `data-contrast`
5. 有力引言 → `quote-hero`
6. 数据是表格 → `table`
7. 单句核心陈述 → `hero-statement`
8. 默认 → `bullets`

通用禁止: hero-statement 不得用于 3+ 条目; table 不得用于流程; bullets 不得用于并列对比.

产出 `<workdir>/slide-plan.yaml` (schema 由 `schemas/slide_plan.py` 定义).

**Deterministic 门禁 (强制, 不可跳)**:
```bash
uv run --script <plugin-root>/engine/validate_plan.py <workdir>/slide-plan.yaml --theme <theme> --json
```

校验规则:
1. **内容量**: cards/process/framework/timeline 每 key_point ≥ 80 字; comparison ≥ 100; bullets 总计 ≥ 200; data-contrast 总计 ≥ 80; table rows ≥ 2; hero-statement/quote-hero/story-card 豁免
2. **应用率** (仅 `--theme=huawei`): huawei 18 版式占比, 默认 ≥60% PASS / 30-60% WARN / <30% FAIL

**Exit code**:
- `0`: 全通过
- `1`: 内容量 FAIL — 读 JSON 的 `point_issues`/`total_issue`, 从 content-architecture.yaml source_refs 回溯源材料补充; 连续 3 轮无法通过 → AskUserQuestion 让用户决策
- `2`: 应用率 FAIL — 按 .theme-prompt.md 重新审视 visual_type 选择 (cards-N → cards-6 / kpi-stats / architecture-layered 等); 连续 2 轮未达阈值 → AskUserQuestion

### Stage 4: Render (deterministic) + 可选评审

```bash
uv run python <plugin-root>/engine/render.py <workdir>/slide-plan.yaml --theme <theme> --output <output-path>
```

渲染后再跑一次 validate_plan 防御性检查:
```bash
uv run --script <plugin-root>/engine/validate_plan.py <workdir>/slide-plan.yaml --json
```

仍有 FAIL → 立即停管线, AskUserQuestion 报告.

**视觉评审 (可选, 用户按需)**: v3.4.0 起删除内嵌 LLM 视觉 QA. 用户需要视觉评审时调:
```
/ppt:taste <output-path>
```
ppt:taste skill 用 huawei 锚点库 + 双轴评分 (layout / palette) 给出 actionable 改进项. ppt:create 本身不主动调它.

### 完成

```
PPT 已生成: <output-path>
N 页 | 主题: <theme> | 预设: <preset>
评审 (可选): /ppt:taste <output-path>
调整: /ppt:refine <output-path> <调整指令>
```

## 中间产物

`<output-dir>/.ppt-workdir/` 下:
- `parsed-content.json`
- `content-architecture.yaml`
- `.theme-prompt.md`
- `slide-plan.yaml`
