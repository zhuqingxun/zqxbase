---
name: ppt:theme
description: >-
  PPT 主题管理。支持列表、提取、应用和创建主题。
  当用户提到"PPT 主题""ppt:theme""列出主题""提取主题""应用主题""创建主题"时触发。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 3.0.1
---

# PPT:Theme — 主题管理

管理 PPT 视觉主题（列表/提取/应用/创建）。

## 路径约定

本文档中 `<plugin-root>` 指 plugin 根目录。推导方式：Base directory 的两级父目录（即 `skills/theme/` 的上两层）。执行 bash 命令前，先确定实际路径再替换 `<plugin-root>`。

## 子命令路由

从 `$ARGUMENTS` 解析子命令：

### `list`（列出所有主题）

1. 扫描 `<plugin-root>/themes/` 目录下所有 `.yaml` 文件
2. 读取每个文件的 `name` 和 `description` 字段
3. 以表格形式展示：

```
可用主题：
| 名称           | 描述                                           |
|----------------|------------------------------------------------|
| clean-light    | 浅色简洁主题。白底冷色调，无装饰，适合研究报告 |
| dark-business  | 深色商务主题。深色背景，强对比，现代感         |
| academic       | 学术严谨主题。白色背景，单一 sans-serif        |
| huawei         | 华为胶片风格主题                               |
```

### `extract <template.pptx> [--name <name>]`

从 .pptx 模板文件提取主题为 YAML：

1. 使用 python-pptx 读取模板：
   - 提取 slide master 的背景色
   - 提取 theme part 的配色方案（a:clrScheme）
   - 提取字体方案（a:fontScheme）
   - 分析第一页 slide 的实际字号和间距
2. 映射为主题 YAML 结构：
   - colors: 从 clrScheme 映射
   - typography: 从 fontScheme + 实际使用的字号映射
   - spacing: 从实际元素间距推断
   - visual_preferences: 从形状属性推断（有无阴影/渐变/圆角）
3. 保存到 `<plugin-root>/themes/<name>.yaml`
4. 展示提取结果供用户确认

### `apply <theme> <output.pptx>`

对已有 PPT 切换主题：

1. 读取目标 PPTX 和关联的 slide-plan.yaml（如有）
2. 读取新主题 YAML
3. 更新 slide-plan.yaml 中所有 slides 的 design 字段（替换为新主题参数）
4. 重渲染：
```bash
uv run python <plugin-root>/engine/render.py <workdir>/slide-plan.yaml \
    --theme <new-theme> --output <output-path>
```
5. 如无 slide-plan.yaml，用逆向分析方式（同 ppt:refine）

### `create <name>`

交互式创建自定义主题：

1. 用 AskUserQuestion 逐步收集：
   - 整体风格（浅色/深色/品牌色）
   - 推荐色板：读取 `<plugin-root>/themes/palettes.yaml`，按用户描述的风格/场景匹配推荐 2-3 组
   - 主色调和强调色（支持从色板选择或自定义 hex）
   - 字体配对推荐（中文: YaHei Bold+YaHei / SimHei+SimSun；西文: Georgia+Calibri / Arial Black+Arial / Cambria+Calibri）
   - 装饰偏好（阴影/渐变/圆角）
   - 视觉母题：`card_header_style`（color_bar / left_bar / none）
2. 生成主题 YAML（**必须包含 `visual_elements` 段**）并保存
3. 展示主题预览描述供确认

## 主题 YAML 结构参考

主题文件存放在 `<plugin-root>/themes/`，结构：

```yaml
name: string
description: string
colors:
  background: string        # hex color
  text_primary: string
  text_secondary: string
  accent: string
  accent_secondary: string
  warning: string
  card_fills: list[string]  # 5 个卡片填充色
typography:
  title_font: string
  body_font: string
  title_size_pt: int
  subtitle_size_pt: int
  body_size_pt: int
  caption_size_pt: int
spacing:
  slide_margin_inches: float
  element_gap_inches: float
  line_spacing: float
visual_preferences:
  shadow: bool
  gradient: bool
  rounded_corners: bool
  corner_radius_inches: float
visual_elements:
  footer_show_page_number: bool
  footer_show_chapter: bool
  footer_height_inches: float
  card_header_height_inches: float
  card_header_style: string        # "color_bar" | "left_bar" | "none"
  card_content_alignment: string   # "top" | "center"
  metric_container_style: string   # "rounded_rect" | "circle" | "none"
  metric_value_size_pt: int
  metric_label_size_pt: int
  description_size_pt: int
  description_color: string | null
```
