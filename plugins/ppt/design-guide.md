# PPT 设计指南

供 ppt:create 和 ppt:refine 共同引用的设计知识库。

---

## 1. 设计哲学

### 不做无聊的胶片

每页必须有视觉元素（形状、色块、数据指标容器、表格），纯文本页面不可接受。
bullets 是最后的选择——优先使用 cards、comparison、data-contrast、process 等结构化布局。

### 色彩主导性

一个颜色占 60-70% 视觉权重（通常是背景色），1-2 个辅助色，一个锐利强调色。
禁止所有颜色平分秋色。

### 暗亮对比

标题页 + 结论页用深色背景，内容页用浅色（"三明治"结构）。
或全程深色营造高级感。禁止全程浅色白底——看起来像未完成的草稿。

### 视觉母题

选定一种标志性元素（圆角卡片、色条标题栏、左侧粗边框等），贯穿全部 slide。
由主题 YAML 的 `visual_elements.card_header_style` 控制。

### 色彩匹配内容

调色板应专为当前演示内容设计。如果换到完全不同的演示文稿仍然"适用"，说明色彩选择不够具体。
参考 `themes/palettes.yaml` 的 10 组话题导向配色。

---

## 2. 每页设计规则

### 内容密度

- 每页至少一个非文本视觉元素（shape / chart / metric container）
- cards/comparison/process 类型的 key_point 必须有 heading（标题+正文分层）
- data-contrast 必须有 metric_value（大号指标）+ metric_label（小标签）
- 非豁免页面（hero-statement/quote-hero/story-card 除外）必须有 description（1-3 句上下文描述）
- 有数据引用的页面必须有 footnote（来源标注）

### 标题规范

- 标题为**行动标题**——传达观点，不只是描述主题
  - 好: "基层人力配置严重失衡" 
  - 差: "基层人力数据"
- 标题 28-36pt bold，左对齐

### 数据展示

- 数据指标用大号字（40-60pt bold）+ 小标签（12-14pt），不要用正文字号展示数字
- 指标放在视觉容器（圆角矩形/圆形）中，不要裸文本漂浮
- 对比数据并排展示，每组有独立容器

### 内容分层

- 卡片/对比列/流程阶段必须有 heading 分层（标题栏 + 正文区）
- heading 用色条或粗体区分，正文用常规字重
- 一个卡片内的信息层级：heading → metric（如有）→ body text

---

## 3. 反模式清单

标记 `[AUTO]` 的规则由 validate_plan.py 自动检测。审美层反模式(黑底/红底/巨字/模板变量泄露)在 `<plugin-root>/anchors.yaml` 的 `antipatterns` 段(AP1-AP5),布局/反模式决策时必查。

### 布局类

- `[AUTO]` **连续 2 页相同 visual_type** — 布局必须多样化，相邻页面应使用不同类型
- **纯文本 bullets 连续超过 1 页** — 应穿插视觉化类型（cards、comparison 等）
- **正文居中对齐** — 正文和列表左对齐，仅标题和指标数字居中

### 内容类

- `[AUTO]` **cards/comparison 的 key_point 无 heading** — 导致内容扁平，缺少视觉层级
- `[AUTO]` **data-contrast 无 metric_value** — 数字和正文字号相同，失去数据冲击力
- `[AUTO]` **非豁免页面无 description** — 标题到内容间大片空白
- **key_point body < 80 字** — 内容过于单薄（已由 validate_plan.py FAIL 级别检测）

### 视觉类

- **标题下加装饰线/色带** — 这是 AI 生成胶片的标志性特征，应避免。用 description 文本和留白替代
- **字号缺乏对比** — 标题 28pt+ 才能与 14-16pt 正文拉开层级
- **所有卡片颜色相同** — 应使用主题的 card_fills 色板做差异化
- **低对比度文字** — 浅色背景上的浅色文字、深色背景上的深色文字都不可接受
- **文本框 padding 未考虑** — 对齐线条或形状与文字边缘时，注意文本框的内边距

---

## 4. 字号规范

| 元素 | 字号 | 字重 | 对齐 | 颜色来源 |
|------|------|------|------|---------|
| Slide 标题 | 28-36pt | Bold | 左对齐 | title_color |
| 描述文字 | 14pt | Regular | 左对齐 | text_secondary |
| 正文 | 14-16pt | Regular | 左对齐 | body_color |
| 卡片 heading | 14-16pt | Bold | 左对齐 | 白色（色条内）或 title_color |
| 指标数字 | 40-60pt | Bold | 居中 | accent_color |
| 指标标签 | 12-14pt | Regular | 居中 | body_color |
| 脚注/来源 | 10-12pt | Regular | 左对齐 | text_secondary |
| 页码 | 10pt | Regular | 右对齐 | text_secondary |
| 章节标注 | 10pt | Regular | 居中 | text_secondary |

---

## 5. 间距规范

| 元素 | 间距 |
|------|------|
| 页面边距 | 由主题 slide_margin_inches 控制（通常 0.4-0.5"） |
| 标题到 description | 0.15" |
| description 到内容区 | 0.25" |
| 卡片间距 | 由主题 element_gap_inches 控制（通常 0.2-0.25"） |
| 内容区到页脚 | 0.15" |
| 页脚高度 | 由主题 footer_height_inches 控制（通常 0.35"） |
