---
name: ppt:theme
description: >-
  PPT 主题管理。支持列表、提取、应用和创建主题。
  当用户提到"PPT 主题""ppt:theme""列出主题""提取主题""应用主题""创建主题"时触发。
argument-hint: "[list|extract|apply|create] [<template.pptx>|<theme>] [--name <name>]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 3.0.2
---

# PPT:Theme — 主题管理

管理 PPT 视觉主题（列表/提取/应用/创建）。

## 路径约定

本文档中 `<plugin-root>` 指 plugin 根目录。推导方式：Base directory 的两级父目录（即 `skills/theme/` 的上两层）。执行 bash 命令前，先确定实际路径再替换 `<plugin-root>`。

## v3.0.x 主题架构

自 v3.0.0 起，主题采用**目录化**组织，一个主题一个目录：

```
<plugin-root>/themes/
└── <theme-name>/
    ├── tokens.yaml     # 颜色 / 字体栈 / 字号阶梯
    ├── layouts.yaml    # 画布 / 18 visual_type 专属布局参数
    ├── README.md       # 主题说明与版式速查
    └── reference/      # 开发者目测基准（HTML 模板 + CSS，运行时不读取）
```

**当前唯一内置主题**：`huawei`（参考华为胶片风格，红黑配色，18 个结构化版式，1920×1080 画布）。

**已删除主题**（v2.x 遗留）：`clean-light` / `academic` / `dark-business` / `palettes.yaml`。`engine/render.py` 的 `_REMOVED_THEMES` 常量会对这些名字抛 `ValueError`。

**fallback 契约**：

| 调用 | 行为 |
|---|---|
| 未传 `--theme` | INFO 日志 + 加载 `huawei` |
| `--theme huawei` | 正常加载 |
| `--theme clean-light` / `academic` / `dark-business` | `ValueError`（已删除的旧主题） |
| `--theme <未知目录>` | `FileNotFoundError` |

## 子命令路由

从 `$ARGUMENTS` 解析子命令：

### `list`（列出所有主题）

1. 扫描 `<plugin-root>/themes/` 下的**子目录**（每个目录是一个主题）
2. 对每个主题目录：
   - 从 `tokens.yaml` 读取 `colors.primary` / `fonts.sans` 作为快速特征
   - 从 `README.md` 首段读取主题描述（首个 `## 定位` 或文档起始段落）
3. 以表格形式展示：

```
可用主题：
| 名称    | 主色         | 字体栈                              | 描述                                      |
|---------|--------------|-------------------------------------|-------------------------------------------|
| huawei  | `#C7000B`    | Inter → Noto Sans SC → YaHei        | 参考华为胶片风格，18 版式，1920×1080     |
```

如果 `themes/` 下只有 `huawei/`（v3.0.x 默认状态），明确提示："当前唯一内置主题。需要其他风格可用 `create` 创建新主题。"

### `extract <template.pptx> [--name <name>]`

从 .pptx 模板文件提取**基础主题令牌**（tokens），layouts 从 huawei 继承。

**v3.0.x 限制**：.pptx 没有 18 版式的概念，extract 只能提取颜色/字体/字号，无法生成完整的 `layouts.yaml`。提取后的新主题在 18 版式渲染上会沿用 huawei 的布局参数（仅视觉令牌不同）。

1. 使用 python-pptx 读取模板：
   - 提取 slide master 的背景色（→ `colors.background` / `colors.paper`）
   - 提取 theme part 配色方案 a:clrScheme（→ `colors.primary` 等）
   - 提取 theme part 字体方案 a:fontScheme（→ `fonts.sans[0]`）
   - 抽样第 1 页实际字号（→ 推断 `type_scale_px`）
2. 生成目录 `<plugin-root>/themes/<name>/`：
   - `tokens.yaml`：填充提取到的令牌 + 保留 huawei 的旧兼容层结构（`typography` / `spacing` / `visual_preferences` / `visual_elements`）
   - `layouts.yaml`：**直接复制** `themes/huawei/layouts.yaml`（layouts 结构需要 18 版式完整定义，无法从 .pptx 推导）
   - `README.md`：骨架文档，注明"从 `<template.pptx>` 提取，layouts 继承自 huawei，如需定制请手工调整 layouts.yaml"
3. 展示提取的 tokens 表格供用户确认
4. 提醒：如果用 `--theme <name>` 生成 PPT 后视觉仍偏华为风，说明 layouts 参数（间距/字号/版式结构）未定制，需手工细化 `layouts.yaml`

### `apply <theme> <output.pptx>`

对已有 PPT 切换主题（重渲染）：

1. 读取目标 PPTX 的关联 `slide-plan.yaml`（`<pptx所在目录>/.ppt-workdir/slide-plan.yaml`）
2. 验证目标 `<theme>` 存在（`<plugin-root>/themes/<theme>/` 目录存在且含 tokens.yaml + layouts.yaml）
3. 修改 `slide-plan.yaml` 的 `meta.theme` 字段为 `<theme>`
4. 重渲染：
```bash
uv run python <plugin-root>/engine/render.py <workdir>/slide-plan.yaml \
    --theme <theme> --output <output-path>
```
5. 如无 slide-plan.yaml → 退回到 `ppt:refine` 的逆向分析路径生成 slide-plan 后再 apply

**注意**：不同主题的 `layouts.yaml` 可能有不同的版式参数（字号/间距），切换主题后各 slide 的视觉效果可能差异显著。如果源主题用了目标主题未定义的 visual_type，会报 `ValueError`。

### `create <name>`

交互式创建自定义主题。v3.0.x 下 create 的本质是**复制 huawei 作为起点**再让用户改 tokens：

1. 用 AskUserQuestion 逐步收集：
   - **主色调**（hex，影响 tokens.colors.primary）
   - **深色/浅色变体**（自动生成或用户指定）
   - **字体栈**（西文优先字体，例如 Inter / SF Pro / Roboto；中文自动回退 Noto Sans SC → Microsoft YaHei）
   - **强调色**（accent，用于 trend / highlight）
2. 执行：
   - 创建目录 `<plugin-root>/themes/<name>/`
   - 复制 `themes/huawei/layouts.yaml` 和 `themes/huawei/README.md` 到新目录（保留 18 版式参数原样）
   - 生成 `tokens.yaml`：
     - `colors`：用户选择的新色 + 自动生成的 ink/paper/rule 灰度梯度
     - `fonts.sans`：用户选择的字体栈
     - `type_scale_px`：默认复用 huawei（可后续细化）
     - 旧兼容层（`typography` / `spacing` / `visual_preferences` / `visual_elements`）：同步新色
3. 展示生成结果，提示用户：
   - 如果要定制间距/字号/版式结构，手工编辑 `layouts.yaml`
   - 跑一次 `ppt:create --theme <name>` 验证视觉效果
   - reference/ 目录未自动生成，如需 HTML 目测基准需手工准备

**不推荐**新手直接 create——不修改 layouts.yaml 的话视觉效果和 huawei 差异有限（仅变色/字体）。如果需要显著不同的视觉流派（极简 / 学术 / 科技），建议基于 huawei 的 layouts 做减法或者请求新主题的正式开发。

## 主题文件结构参考

### tokens.yaml 结构

```yaml
# 新 renderer 读
colors:
  primary: "#..."           # 主色
  primary_dark: "#..."
  primary_soft: "#..."
  ink: "#..."               # 正文黑
  ink_soft: "#..."
  ink_mute: "#..."
  ink_dark: "#..."          # 章节深底
  rule: "#..."              # 分割线
  rule_soft: "#..."
  paper: "#..."             # 页底
  paper_2: "#..."
  paper_3: "#..."           # 表头
  accent: "#..."
  ok: "#..."
  warn: "#..."
  # 旧 renderer 兼容别名（必填，与上方同值）
  background: "#..."
  text_primary: "#..."
  text_secondary: "#..."
  accent_color: "#..."

fonts:
  sans:
    - "Inter"               # 西文优先
    - "Noto Sans SC"        # 中文回退 1
    - "Microsoft YaHei"     # 中文回退 2
  mono:
    - "JetBrains Mono"

type_scale_px:              # @ 1920×1080
  cover: 108
  section: 84
  title: 54
  subtitle: 36
  h4: 28
  body: 24
  small: 20
  micro: 16
  nano: 14

# 旧 25 renderer 兼容层（§O7，必填保持旧 renderer 可读）
typography:
  title_font: string
  body_font: string
  title_size_pt: int
  subtitle_size_pt: int
  body_size_pt: int
  caption_size_pt: int
  footnote_size_pt: int

spacing:
  slide_margin_inches: float
  element_gap_inches: float
  card_padding_inches: float
  line_spacing: float

visual_preferences:
  corner_radius_inches: float
  rounded_corners: bool
  show_footer: bool
  show_page_number: bool
  divider_weight_pt: float

visual_elements:
  card_fill: string
  card_stroke: string
  divider_color: string
  bullet_marker: string
  emphasis_bar_color: string
```

### layouts.yaml 结构

```yaml
canvas:
  width_px: 1920
  height_px: 1080
  padding_top_px: int
  padding_left_px: int
  padding_right_px: int
  padding_bottom_px: int

# 每个 visual_type 的专属布局参数（18 个版式各一段）
cover_left_bar:
  bar_width_px: int
  title_size_px: int
  subtitle_size_px: int
  ...

toc: {...}
section_divider_dark: {...}
kpi_stats: {...}
matrix_2x2: {...}
architecture_layered: {...}
timeline_huawei: {...}
process_flow_huawei: {...}
swot: {...}
roadmap: {...}
pyramid: {...}
heatmap_matrix: {...}
thankyou: {...}
cards_6: {...}
rings: {...}
personas: {...}
risk_list: {...}
governance: {...}
```

完整字段值见 `themes/huawei/layouts.yaml`。每个版式的字段契约由 `schemas/variants.py` 定义，强约束断言见 `tests/pixel/assert_tokens_match.py`。

## 参考资料

- **18 版式速查表**：`themes/huawei/README.md` §"18 个可用版式速查"
- **版式字段契约**：`schemas/variants.py`（Pydantic 子模型）
- **版式参数默认值**：`themes/huawei/layouts.yaml`
- **HTML 参考模板**：`themes/huawei/reference/templates/`（25 页开发者目测基准）
