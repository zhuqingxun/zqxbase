# Huawei Theme

参考华为胶片风格的 PPT 主题。18 个结构化版式，咨询级视觉质量。

## 定位

本主题为 `ppt` 插件当前**唯一内置主题**。通过目录化组织 tokens / layouts / reference 三类资产，支持像素级贴近参考华为胶片风格的视觉表达。未指定 `--theme` 时 engine 自动 fallback 到 `huawei`。

## 核心色（tokens.colors）

| 用途 | 键 | 色值 |
|---|---|---|
| 主红 | `primary` | `#C7000B` |
| 深红 | `primary_dark` | `#8A0008` |
| 浅红 | `primary_soft` | `#FDECEE` |
| 正文黑 | `ink` | `#1F1F1F` |
| 次级灰 | `ink_soft` | `#4B4B4B` |
| 辅助灰 | `ink_mute` | `#9A9A9A` |
| 章节深底 | `ink_dark` | `#2A2A2A` |
| 分割线 | `rule` | `#D9D9D9` |
| 柔和线 | `rule_soft` | `#ECECEC` |
| 页底白 | `paper` | `#FFFFFF` |
| 浅底灰 | `paper_2` | `#F4F4F4` |
| 表头灰 | `paper_3` | `#EAEAEA` |
| 强调橙 | `accent` | `#D97706` |

## 字体栈（tokens.fonts.sans）

`Inter → Noto Sans SC → Microsoft YaHei`。西文优先 Inter，中文自动回退系统字体。

## 画布（layouts.canvas）

`1920 x 1080`，四侧 padding 分别为 `top=88 / left=96 / right=96 / bottom=76`（px @ 16:9）。

## 18 个可用版式速查

所有版式通过 `visual_type` 字段声明。字段契约见 `schemas/variants.py`。

| visual_type | 一句话用法 | 最小字段 |
|---|---|---|
| `cover-left-bar` | 封面，左侧 16px 红条 + 108px 主标题 | `title` |
| `toc` | 目录页，3-8 章节编号列表 | `chapters[3..8]` |
| `section-divider-dark` | 章节切换页，深底 + 360px 红色大数字 | `big_number`, `title` |
| `kpi-stats` | 3-6 个 KPI 横排统计板（96px 大数字 + 标签） | `kpis[3..6]` |
| `matrix-2x2` | 战略 2x2 矩阵，双轴 + 四象限 | `axis`, `quadrants[4]` |
| `architecture-layered` | 2-6 层 x 1-6 cell 分层架构图 | `layers[2..6]` |
| `timeline-huawei` | 华为风格横向时间线，3-6 阶段 | `phases[3..6]` |
| `process-flow-huawei` | 流程图，3-6 步骤箭头串联 | `steps[3..6]` |
| `swot` | SWOT 四象限矩阵 | `quadrants{s,w,o,t}` |
| `roadmap` | 路线图，3-5 阶段列 x 1-5 泳道 | `phases[3..5]`, `rows[1..5]` |
| `pyramid` | 3-5 层金字塔 + 侧栏描述 | `levels[3..5]` |
| `heatmap-matrix` | 热力矩阵，3-6 列 x N 行（0-5 打分） | `columns[3..6]`, `rows[]` |
| `thankyou` | 致谢页，360px "Thank you" + 联系方式 | `title`, `emphasis` |
| `cards-6` | 六宫格卡片（3 列 x 2 行） | `cards[6]` |
| `rings` | 同心环，2-4 环 + 右侧编号说明 | `rings[2..4]` |
| `personas` | 角色卡，2-4 个 persona | `personas[2..4]` |
| `risk-list` | 风险清单，2-6 项含严重度 | `risks[2..6]` |
| `governance` | 治理架构，顶部主体 + 2-4 下级单元 | `top`, `units[2..4]` |

## 最小可运行示例

以下是一个 2 slide 的 `slide-plan.yaml` 片段，展示封面 + KPI 面板：

```yaml
meta:
  title: "示例方案"
  preset: "research-report"
  theme: "huawei"

narrative:
  thesis: "通过结构化版式表达核心观点"
  arc: "背景 → 数据 → 结论"
  total_slides: 2

slides:
  - id: 1
    role: title
    content:
      title: "示例方案"
    visual_type: cover-left-bar
    variant:
      visual_type: cover-left-bar
      eyebrow: "研究报告"
      title: "示例方案"
      emphasis: "2026"
      subtitle: "副标题占位"
      meta:
        - { label: "出品方", value: "{团队名}" }
        - { label: "版本", value: "v1.0" }

  - id: 2
    role: data
    content:
      title: "核心指标"
    visual_type: kpi-stats
    variant:
      visual_type: kpi-stats
      title: "核心指标"
      subtitle: "Q1 关键数据"
      kpis:
        - { label: "新增用户", value: "1.2M", unit: "人", trend: up, trend_text: "YoY +18%" }
        - { label: "留存率",   value: "86.5", unit: "%",  trend: flat }
        - { label: "响应延迟", value: "120",  unit: "ms", trend: down, trend_text: "-24ms" }
```

## 目录结构

```
themes/huawei/
├── tokens.yaml         # 颜色 / 字体 / 字号
├── layouts.yaml        # 画布 / 每版式专属布局参数
├── README.md           # 本文件
└── reference/
    ├── assets/         # 原始 CSS/JS（脱敏版）
    ├── templates/      # 25 个 HTML 样式参考（脱敏版）
    ├── screenshots/    # 截图目录
    ├── deck-stage.js   # 舞台演示脚本（脱敏版）
    └── styles.css      # 舞台样式（脱敏版）
```

`reference/` 下的 HTML 是**开发者目测对照基准**，不会被运行时读取。

## fallback 契约

| 调用场景 | 行为 |
|---|---|
| 未传 `--theme` | INFO 日志 + 加载 huawei |
| `--theme huawei` | 正常加载 |
| `--theme clean-light` / `academic` / `dark-business` | `ValueError`（已删除的旧主题） |
| `--theme foo-bar`（未知） | `FileNotFoundError` |

详见 `engine/render.py` 的 `load_theme` 实现和 PRD §7.3.1。

## 设计约束（强约束项）

这些值在 `tests/pixel/assert_tokens_match.py` 中断言：

- 封面主标题 108px / 副标题 34px
- 章节分隔页大数字 360px
- 左红条宽 16px
- KPI 数值字号 96px
- 所有 padding 按 `canvas` 配置
- 色值严格等于 `tokens.colors` 中定义

## 二次开发

如需新增版式：

1. 在 `schemas/variants.py` 新增 `XyzContent(BaseModel)`，带 `visual_type: Literal['xyz']`
2. 加入 `VariantUnion` 和 `VARIANT_TYPES`
3. 在 `schemas/slide_plan.py` 的 `valid_types` 补上 `'xyz'`
4. 在 `engine/renderers_huawei.py` 写 `@register_renderer('xyz')` renderer
5. 在 `layouts.yaml` 加 `xyz:` 布局参数
6. 在 `themes/huawei/reference/templates/` 补充一个 HTML 参考图（可选）
7. 更新本 README 的"18 个可用版式速查"表格

参考华为胶片风格设计语言：以红黑灰为主色、结构化布局、克制的视觉装饰。
