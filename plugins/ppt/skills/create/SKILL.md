---
name: ppt:create
description: >-
  从目录或文件一键生成最高质量 PPT。支持 Markdown 输入和图片资产。
  当用户提到"生成 PPT""做 PPT""创建演示文稿""ppt:create"时触发。
  也适用于: 用户提供了 markdown 文件或目录并要求转化为 PPT 的场景。
argument-hint: "<输入路径> [--preset <name>] [--theme <name>] [--output <path>] [--engine codex|renderer] [--compare] [--cover-image] [--style-ref <pptx>] [--no-style-ref]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
version: 3.9.5
---

# PPT:Create — 一键生成最高质量 PPT

## v3.5.0 产线工程化说明

v3.5.0 把产线从"会话即兴串联 parse/architect/plan/render"改造成**命令式工程流程**: 由 `engine/orchestrator.py` 短命状态机 CLI 统一编排, 每次运行自动归档全部中间产物到独立 run 目录 (`.ppt-workdir/runs/<timestamp>/`), 并支持固定 fixture 回放整条产线 (CI 0 LLM 依赖). orchestrator 只做编排 + 归档 + 校验调度, **LLM 智能 (architect 内容架构 / plan 视觉规划) 仍保持在会话层** — orchestrator 在每个 LLM gate 暂停退出 (exit 3 = NEED_LLM), 会话产出 YAML 后 `resume` 继续推进.

继承 v3.4.0: 删除所有非 deterministic reviewer, 保留 deterministic 校验 (`validate_plan` 内容量 + 应用率门禁) + 1 个用户确认 gate, 视觉评审交给独立的 `/ppt:taste` skill (后置, 用户按需调用).

四阶段流水线保留 (parse → architect → plan → render), 每阶段仅 deterministic 校验 + 失败 fail-fast, 不再做 LLM self-review.

## 路径约定

`<plugin-root>` 指 plugin 根目录, 推导: skills/create/ 的两级父目录. 执行 bash 前替换为实际绝对路径.

## 参数解析

从 `$ARGUMENTS` 中解析:
- **输入路径** (必需): 目录路径或文件路径
- `--preset <name>`: 内容预设 (默认 `research-report`), 可选值见 `<plugin-root>/presets/`
- `--theme <name>`: 视觉主题 (默认 `huawei`, v3.4.0 仅 huawei). 旧主题 (`clean-light` / `academic` / `dark-business`) 显式传入会 `ValueError`
- `--output <path>`: 输出路径 (默认 `./output/<input-name>.pptx`)
- `--engine codex|renderer` (可选): 强制指定引擎. 缺省由 Step 0 路由 (codex 可用即 codex). 与 `--compare` 互斥
- `--compare` (可选): 同输入串行跑双引擎 + taste 双报告 + 对比摘要. 与 `--engine` 互斥
- `--cover-image` (可选): renderer 线增强 — 启动前用 codex imagegen 生成封面摄影图, cover 页消费
- `--style-ref <pptx>` (可选): codex 线的软性风格参考 PPTX (措辞固定 "仅作风格参考, 不强制对齐")
- `--no-style-ref` (可选): codex 线强制不带风格参考 (覆盖本机默认)

## 执行流程 (orchestrator 编排)

v3.5.0 起由 `engine/orchestrator.py` 短命状态机统一编排. 你 (会话 Claude) 的职责是: 在 orchestrator 暂停于 LLM gate 时 (exit 3), 按 run 目录下的 `prompt-context.md` 产出对应 YAML, 然后 `resume`. 不再手动逐个调 parse/prompt_assembler/validate_plan/render.

v3.6.0 起新增 codex 引擎线 (gpt-5.5 + presentations 插件, 编辑级 deck): Step 0 先路由, codex 可用默认走 codex 线, 不可用静默走下方 renderer 线 (Step 1-5). codex 引擎契约与坑清单见 `<plugin-root>/references/codex-engine.md`.

> **引擎定位 (2026-06-23 F4 对照实验验证)**: codex 是**质量主力**, renderer 是**离线 fallback**。F4 对照 (同输入分别跑 codex/renderer + ppt:taste 双轴评分 + 用户肉眼裁决) 结论: codex 最终质量**明显优于** renderer (codex 满意可交付、renderer 基本不可用; taste 双轴 codex layout 3.86 > renderer 3.33, 差距全在 layout —— renderer 自适应母版在 4-5 项时布局崩坏 / 标题栏容不下长标题)。故「codex 可用即走 codex」不是任意默认、而是经实测验证的质量优先级; renderer 仅在 codex 不可用时优雅降级。**维护提示**: 优化 renderer 内部视觉/布局对「最终 PPT 质量」边际价值有限, 不建议为此大投入。

### Step 0: 引擎路由

```bash
uv run --script <plugin-root>/scripts/detect_codex.py
```

- exit 0 且未指定 `--engine renderer` → **codex 线** (默认品位优先, 见「codex 线流程」节)
- exit 1 → **静默走 renderer 线** (现有 Step 1-5, 零提示噪音 — 这是路由不是降级, 不要向用户解释 codex 为何不可用)
- `--engine codex` 但 detect exit 1 → 把 stdout JSON 的 reason 报给用户, 停 (显式要求才报错)
- `--compare` → 走「--compare 对比编排」节 (与 `--engine` 互斥, 同时传入时报用法错误)

### codex 线流程

a. **数据出境告知**: 启动告知固定带一句「源材料将上传 OpenAI 云端处理, 预计 8-30 分钟」. 仅当输入路径命中敏感信号时, 才先 AskUserQuestion 确认 — 敏感信号: 路径命中用户全局 `~/.claude/knowledge/codex.md`「ppt-codex-fusion 封装入口」节登记的敏感目录 (含风格参考所在目录)、文件名含 内部/机密/confidential、或用户语境标注敏感. 选项: ① 继续 codex ② 改走 renderer (材料不出境) ③ 中止. 无敏感信号时不额外交互.

b. **style-ref 解析** (优先级从高到低):
   1. 显式 `--style-ref <路径>` (Read 确认存在才用, 不存在则警告并按缺省继续)
   2. 本机默认: Read 用户全局 `~/.claude/knowledge/codex.md` 的「ppt-codex-fusion 封装入口」节取登记的参考文件路径, **确认文件存在**才传
   3. `--no-style-ref` 强制不带 (覆盖以上两级)
   - 本 SKILL.md 与插件源码不硬编码任何本机路径; 风格参考语义是软性的 (prompt 措辞由 codex_ppt.py 固化为 "仅作风格参考, 不强制对齐")

c. **调用** (run_in_background 跑, 启动后告知用户预计耗时, 完成后续跑 d):

```bash
uv run --script <plugin-root>/scripts/codex_ppt.py --input <输入路径> --output-dir <输出目录> \
    --topic <主题> [--pages N-M] [--style-ref <路径>]
```

   exit code 语义: 0 = 成功 (stdout 最后一行 = PPTX 绝对路径); 1 = codex 运行失败; 2 = 检测/用法错误; 3 = 产物验证失败. 详见 references/codex-engine.md.

d. **taste 闭环**: codex_ppt exit 0 → 自动按 `/ppt:taste <pptx路径> --mode general` 流程产报告 (报告与 deck 同目录) → 汇报双轴分数 + Top 改进项, 然后 `Start-Process <pptx路径>` 打开成品给用户.

e. **失败三选项**: codex_ppt exit 1/3 → 报 stderr 原因 → AskUserQuestion: ① 重试 codex ② 降级 renderer (走现有 Step 1-5) ③ 中止. **禁止默默切换引擎**.

### --cover-image (renderer 线增强)

renderer 线启动前 (Step 1 之前) 调:

```bash
uv run --script <plugin-root>/scripts/codex_image.py --theme <主题> --output <输入目录>/assets/cover-generated.png --kind cover
```

- 成功 (exit 0) → Step 4 视觉规划时在 cover 页 `content.image_ref` 填该 PNG 路径 (renderer 的 cover-left-bar 版式会在右侧区消费, 即「封面摄影版」)
- 失败 (exit 1/2/3) → 警告一句 + 无图 cover 继续 (不阻塞产线)

### --compare 对比编排

纯编排 (无新脚本), 串行执行:

1. **codex 线** (跳过失败三选项 — 失败只记原因, 不交互)
2. **renderer 线** (现有 Step 1-5 完整走完, 含 architect 用户确认 gate)
3. 各自 taste: codex 产物 `--mode general`, renderer 产物 `--mode anchor`
4. 按 `<plugin-root>/references/codex-engine.md` 的「对比报告模板」汇总落 `<输出目录>/compare-report.md` (汇总表: 引擎 / taste layout 均分 / palette 均分 / 页数 / 耗时 / 文件大小 + 结论建议段)
5. 任一引擎失败 → 单引擎报告 + 标注缺失原因 (对比降级为单列, 不中止)

### Step 1: 启动产线 (orchestrator run)

```bash
uv run --script <plugin-root>/engine/orchestrator.py run <input-path> --preset <preset> --theme <theme> --output <output-path>
```

orchestrator 会: 建 run 目录 (`<output-dir>/.ppt-workdir/runs/<timestamp>/`) → 跑 parse → 组装 `02-architect/prompt-context.md` → **exit 3 (NEED_LLM)** 暂停, 等你产出 architect 内容架构.

- exit 3 = 正常暂停在 architect gate, 读 `state.json` 的 `awaiting` 字段知道该产出哪个文件
- exit 1 = parse 失败, 读 `error.json` 报错给用户, 停管线
- exit 2 = 用法错误 (路径不存在等)

### Step 2: 内容架构 (你作为内容架构师 + 用户确认 gate)

**Read `<run-dir>/02-architect/prompt-context.md`** (orchestrator 已注入 parsed 摘要 + preset + design-guide 全文). 按其中"你的任务"段:
1. 全局分析输入材料, 提炼核心论点 / 叙事线
2. 做内容取舍, 划分章节, 设计叙事弧线
3. 为每页规划结构化内容要点 (每 point 的 body **80-150 字**, 含数据 / 案例 / 论证细节)
4. 为每页撰写 description (1-3 句上下文), 数据引用页标 footnote

产出 `<run-dir>/02-architect/output.yaml` (= content-architecture, schema 见 prompt-context.md "产出格式" 段).

**内容量硬约束** (Step 4 的 validate_plan 会再次拦截, 此处先尽力保证):
- `content_points.body` 字段 80-150 字
- cards / comparison / process 类型 content_points **必须有 heading**
- data-contrast **必须有 metric_value + metric_label**
- 非豁免页面 (hero-statement / quote-hero / story-card 除外) **必须有 description**
- 有数据引用的页面 **必须有 footnote**

**章节标题建议** (advisory, 不阻塞): resume 时调 `validate_architecture` 把 chapter title <10 字 / required_sections 未覆盖等内容 issues 写入 `02-architect/validation.json`, 但**不 fail** — 这些是建议而非硬门 (协议层只硬卡 output.yaml 缺失/空/非法 YAML). 仍建议 chapter title 用完整句 (action_title 风格), 短词章节名 (如"封面"/"目录") 在 `role` 字段标注对应角色, 以提升输出质量.

**用户确认 gate (必须 AskUserQuestion, 不可跳)**:

输出架构摘要 (核心论点、章节标题 + 核心信息、预计页数、被裁剪内容清单), 然后 AskUserQuestion:

- 选项 1: "确认, 进入视觉规划"
- 选项 2: "需要调整" (用户输入修改意见后重做 Architect, 覆写 output.yaml)
- 选项 3: "查看某章节的详细 content_points"

### Step 3: 推进到视觉规划 (orchestrator resume)

用户确认后:
```bash
uv run --script <plugin-root>/engine/orchestrator.py resume <run-dir>
```

orchestrator 会: 校验 `02-architect/output.yaml` (协议层: 存在性 + YAML/schema 合法性) → 通过则把 validate_architecture 内容 issues 记入 validation.json (advisory) + 组装 `03-plan/theme-prompt.md` + `03-plan/prompt-context.md` → **exit 3** 暂停, 等你产出 slide-plan.

- exit 3 = architect gate 通过 (含内容 advisory issues 时也推进), 暂停在 plan gate
- exit 1 = **协议层**失败 (output.yaml 缺失/空/非法 YAML), 读 `error.json` (rule=protocol.*) 修复后重新 resume

### Step 4: 视觉规划 (你作为视觉规划师 + deterministic 门禁)

**Read `<run-dir>/03-plan/prompt-context.md` 和 `<run-dir>/03-plan/theme-prompt.md`**. 后者由 `engine/prompt_assembler.py` 从 `themes/<theme>/preferences.yaml` + `schemas/variants.py` 派生, 含 6 类硬约束 + 软引导 + 母版字段速查 + 退回链 + path X 字段填法. 优先选无后缀自适应母版 (cards / process / comparison): **选母版给数据, 布局由数据量自动派生, 不要猜具体 N** (旧 cards-N / process-N-phase / comparison-N 仍兼容但 deprecated, 不推荐新用).

锚点库使用 (可选参考): `<plugin-root>/anchors.yaml` 的 `usage_by_skill.ppt:create` — 决定 layout 时查 layout_only / extended 找参考案例 (学 layout 不学 palette, 按原则 P2); 生成前对照 antipatterns AP1-AP5 主动避免反模式.

**所有视觉规划决策必须严格遵循 `theme-prompt.md`**. 为每页:
1. 按 theme-prompt.md 硬约束 + 软引导选 visual_type (通用 fallback 决策树见 prompt-context.md)
2. key_points 用结构化对象格式 (heading + body, data-contrast 加 metric_value + metric_label)
3. 每页有 description (豁免类型除外), 数据页有 footnote
4. 连续 2 页不得用相同 visual_type (布局多样性)

**母版字段填法 (path X)**:
- 公共字段 (title / subtitle / description) → `slide.content`
- 专属字段 (kpis / chapters / layers / steps / phases / quadrants / personas / risks / units / 自适应母版的 points / ...) → `slide.variant`
- 不要把专属字段平铺到 slide.content 顶层

产出 `<run-dir>/03-plan/output.yaml` (= slide-plan, schema 由 `schemas/slide_plan.py` 定义).

### Step 5: 推进到渲染 (orchestrator resume)

```bash
uv run --script <plugin-root>/engine/orchestrator.py resume <run-dir>
```

orchestrator 会: `SlidePlan.from_yaml` pydantic 校验 → `validate_plan` 内容量 + 应用率门禁 → 通过则 render → deck 落 `04-render/deck.pptx` 并拷到 `--output` → **exit 0 (DONE)**.

**失败处理 (读 `error.json` 的 `rule` 字段区分)**:
- exit 1, `rule=schema.variant_validation`: variant 字段不合法, 按 theme-prompt.md path X 修正后覆写 output.yaml 重新 resume
- exit 1, `rule=content_volume.*`: 内容量 FAIL — 读 `error.json` 的 `message` (含 slide_no + 字数), 从 `02-architect/output.yaml` source_refs 回溯源材料补充 body; **连续 3 轮无法通过 → AskUserQuestion 让用户决策**
- exit 1, `rule=application_rate.fail_below_30`: 应用率 FAIL — 按 theme-prompt.md 重选 visual_type (通用 bullets/table → 自适应 cards/process 或 kpi-stats / architecture-layered 等母版); **连续 2 轮未达阈值 → AskUserQuestion**

> orchestrator 短命无状态, 不计轮数. 重试轮数 (内容量 3 轮 / 应用率 2 轮) 由你 (会话) 据 error.json 自行计数 + 决定何时升级 AskUserQuestion.

**视觉评审 (可选, 用户按需)**: v3.4.0 起删除内嵌 LLM 视觉 QA. 用户需要视觉评审时调:
```
/ppt:taste <output-path>
```
ppt:taste skill 用 huawei 锚点库 + 双轴评分 (layout / palette) 给出 actionable 改进项. ppt:create 本身不主动调它.

### 完成

orchestrator exit 0 后 (codex 线则 codex_ppt exit 0 + taste 闭环完成后), 报告给用户:
```
PPT 已生成: <output-path>
N 页 | 引擎: <codex|renderer> | 主题: <theme> | 预设: <preset>
run 目录 (全产物归档): <run-dir>
评审 (可选): /ppt:taste <output-path>
调整: /ppt:refine <output-path> <调整指令>
```

## 中间产物 (run 目录布局)

每次运行归档到独立 run 目录 `<output-dir>/.ppt-workdir/runs/<timestamp>/`:
- `manifest.json` — 运行元数据 (mode / input_sha256 / 各阶段状态)
- `state.json` — 状态机当前位置 (current_stage / awaiting / next_action)
- `error.json` — 仅失败时, 含 stage / slide_no / rule / message / remediation
- `01-parse/parsed-content.json`
- `02-architect/` — `prompt-context.md` (桥接上下文) + `output.yaml` (content-architecture) + `validation.json`
- `03-plan/` — `theme-prompt.md` (决策框架) + `prompt-context.md` + `output.yaml` (slide-plan) + `validation.json`
- `04-render/` — `deck.pptx` + `render-log.json`
- `05-taste/` — 空挂载点 (S3-P1 落 taste-report)

deck 出问题时回放定位: `uv run --script <plugin-root>/engine/orchestrator.py replay <input> --fixture <fixture-dir> --output <path>` (recorded mode, 固定 fixture 回放整条产线, 0 LLM 依赖).
