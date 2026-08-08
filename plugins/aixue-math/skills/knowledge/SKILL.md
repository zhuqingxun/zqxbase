---
name: aixue-math:knowledge
description: >-
  aixue-math 流水线 Stage 2：处理输入 (2) 知识点。从教师用书 / 教学参考书的 PDF 按页码范围
  提取某单元的知识体系，产出面向教案生成的结构化 Markdown。当用户说「提取知识点」「处理教师用书」
  「aixue-math:knowledge」「把教参 100-150 页转成 Markdown」「教师用书结构化」时触发。
  工作区感知：自动写入 02_知识点/extracted/ 并更新 workspace.yaml 的 inputs.knowledge 状态。
  与 aixue-math:textbook 不同，本 skill 的目标读者是"下游教案生成器"，重点抽取
  教学目标、知识结构、教学建议、学情预判、典型错例等**文字性教学策略**，而不是逐图做教学意图标注
  （教师用书中的插图通常是学生教材的复用版，原图解读已在 textbook.md 中完成）。
argument-hint: "<PDF 路径> <起始页> <结束页> [--workspace <root>]"
allowed-tools: Read, Write, Bash, Glob, Grep
version: 0.5.2
version: 0.1.1
---

# aixue-math:knowledge — 教师用书 / 教参 PDF → 结构化知识点 Markdown

> **路径约定**：`{AIXUE_MATH_SCRIPTS}` = aixue-math 插件 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/aixue-math/scripts/workspace_io.py")` 定位，多结果时优先非 `marketplaces/` 路径。

## 为什么这个 skill 存在

`aixue-math:textbook` 处理**学生教材**——内容是教学脚手架（图+活动+情境），核心价值是保留插图的教学意图。

`aixue-math:knowledge` 处理**教师用书 / 教参**——内容是教学指南（知识体系+教学建议+学情分析+错例策略），核心价值是**把教研专家的教学智慧结构化，供下游 `aixue-math:generate` 直接引用**。

两者互补：
- textbook.md 回答"课堂上给学生看什么、做什么"
- knowledge.md 回答"这节课要教什么、怎么教、防什么坑、达到什么水平"

generate 合成教案时，**教学目标、重难点、学生预设、教师调控、设计意图**这些样例中最值钱的字段，主要从 knowledge.md 来。

## 用法

```
/aixue-math:knowledge <PDF 路径> <起始页> <结束页> [--workspace <root>]
```

**必需参数**：

- `<PDF 路径>` 教师用书 PDF 绝对路径
- `<起始页>` PDF 物理页（从 1 开始，包含）
- `<结束页>` PDF 物理页（包含）

**可选参数**：

- `--workspace <root>` 显式指定工作区根；省略时从 cwd 自动发现

教师用书的一个单元通常 20-60 页。**不要自己猜页码范围**——让用户明确指定。

## 执行流程（参考 textbook 的三步工作流）

### 第一步：定位工作区

```bash
if [ -n "$WORKSPACE_ARG" ]; then
  WORKSPACE_ROOT="$WORKSPACE_ARG"
else
  WORKSPACE_ROOT=$(uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py find-workspace-root "$PWD")
fi
test -f "$WORKSPACE_ROOT/.aixue/workspace.yaml" || exit 1
```

若未找到工作区，报错：`未找到 aixue-math 工作区，请先运行 /aixue-math:init <课时名>` 并 exit 1。

### 第二步：截取与渲染

直接复用 `extract_pages.py`（和 textbook 同一脚本）：

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/extract_pages.py \
  --pdf "<PDF 路径>" \
  --start <起始页> --end <结束页> \
  --output-dir "$WORKSPACE_ROOT/02_知识点/extracted" \
  --chapter-name "<workspace.title>_教师用书" \
  --dpi 400
```

产物目录：

```
02_知识点/extracted/
├── <title>_教师用书_章节.pdf
├── pages/page_XXX.png
└── assets/
```

### 第三步：视觉核对 + 分批分析

**第一动作**：Read `02_知识点/extracted/pages/` 下第一页，**确认这是不是预期的单元起始页**。教师用书前有目录、前言、致教师的话等若干页，起始页码容易偏。不匹配就调整页码范围重跑 Step 2。

教师用书典型有 20-60 页的量，一次性 Read 全部会爆 token。采用**分批扫读 + 逐批产出临时片段 + 最终合成**策略：

1. **先粗扫**：Read 首、尾、中间 3-4 页，摸清整个单元的结构（有几个小节？每小节大致几页？评价/附录在哪里？）
2. **分批精读**：按小节分批 Read，每批 6-10 页。每批产出一份临时片段 `_tmp_section_N.md`
3. **最终合成**：把所有临时片段合成一份结构化总 MD，删除中间临时文件

## 视觉分析的核心 prompt（教师用书专版）

**与 textbook 最大区别**：教师用书以文字为主，插图主要是学生教材插图的缩略复用，**不做"画面+教学意图"三轨标注**（重复劳动——textbook.md 已标过），而是重点抽取**文字性教学策略**。

### 抽取目标清单（对每一批 Read 的页面都要覆盖这些目标）

1. **单元教学目标**：教参原文列出的"课程总目标" / "教学目标"（通常在单元前言）
2. **知识脉络**：该单元包含哪些课时？每课时的核心概念？知识结构化图（若有思维导图原图，用文字描述）
3. **每个课时的要素**（教师用书通常对每课时展开 4-8 页）：
   - **教学内容概述**（本课时教什么）
   - **显性知识 / 隐性知识**（分别列出）
   - **教学目标**（细化到本课时）
   - **教学建议**：创设情境、活动设计、核心问题串、师生对话示例
   - **学情预判**：学生常见起点 / 难点 / 误解
   - **教学重难点及突破措施**
4. **典型错例与对策**：教师用书常有"可能出现的问题"章节，全量收集
5. **课后思考/拓展资源**：如果有
6. **单元评价建议**：如何评估教学效果（前测/后测题、表现性评价等）

### 抽取时的简化规则

- **插图**：只在以下情况下提及
  - 教师用书独有的插图（流程图、思维导图、板书示例等）——用文字描述结构
  - 学生教材插图复用的，**只引用 fig_pXX_K 锚点**（如 "对应 textbook.md 的 fig_p36_2"），不重复描述画面
- **公式**：LaTeX
- **教参原文的"教学建议"**：尽量保留原文措辞，这是教研专家的智慧沉淀——不要过度转述

### 分批处理的注意事项

- 每批 Read 前在 Markdown 临时文件中记录"本批覆盖 p.XXX-YYY，属于第 N 小节"
- 每批的抽取产物在同一个临时文件里按上述 1-6 目标结构组织
- 最终合成时，去重、按小节合并、统一术语

## 第四步：产出结构化 knowledge.md

最终产出 `02_知识点/extracted/周长.md`（用 workspace.title 命名，可省略 `_教师用书` 后缀——因为目录已经表明了这是知识点）。

遵循以下 frontmatter 和章节结构：

```markdown
---
source_pdf: <原 PDF 文件名>
pdf_pages: "<起始>-<结束>"
unit: <单元名>
subject: 数学
grade: <年级>
textbook_edition: <教材版本>
publisher: <出版社>
book_type: 教师用书
extracted_at: <YYYY-MM-DD>
extraction_method: Claude Opus 4.7 视觉分析（400 DPI PNG 分批扫读）

# 本 knowledge 可服务于哪些课时
applies_to_lessons:
  - <课时 1 名称>
  - <课时 2 名称>
  - ...
---

# <单元名> · 知识体系（来自教师用书）

## 一、单元整体定位

### 单元在知识体系中的位置
- 前置知识：...
- 本单元作用：...
- 后续衔接：...

### 单元教学目标（教参原文）
1. ...
2. ...

### 核心素养对标（若有）
- ...

## 二、单元结构 · 课时划分

| 课时 | 标题 | 教参页码 | 核心概念 |
|-----|------|---------|---------|
| 1 | ... | p.X | ... |
| 2 | ... | p.Y | ... |

## 三、各课时要素展开

### 课时 1：<名称>

#### 教学内容概述

...

#### 显性知识

- ...

#### 隐性知识（数学思想、核心素养）

- ...

#### 教学目标（本课时）

1. ...
2. ...

#### 教学建议

**情境创设**：
- ...

**核心问题串**（教参建议的课堂问题序列）：
- Q1: ...
- Q2: ...

**关键活动**：
1. ...

**师生对话示例**（教参原文）：
> 师："..."
> 生预设："..."
> 师应对："..."

#### 学情预判

**学生已有基础**：
- ...

**常见困难与误解**：
- ...

**教学重难点及突破措施**：
- 重点：...
- 难点：...
- 措施：...

---

### 课时 2：...

（同上结构）

## 四、典型错例与对策（单元整体）

| 错例/误解 | 原因 | 突破策略 |
|----------|------|---------|
| 例 1：... | ... | ... |

## 五、评价建议

### 前测/学情调研建议
- ...

### 后测/效果评价建议题
- 题 1（基础）：...
- 题 2（变式）：...
- 题 3（综合应用）：...

## 六、拓展资源（若有）
- ...
```

### 关键原则

1. **服务于下游 generate**：优先抽取"学生预设""教师调控""教学意图"类直接可用的教研语言
2. **保留教参原文措辞**：教研专家的描述往往是字斟句酌的，粗暴转述会丢信息
3. **结构化不丢语义**：表格和列表能表达的尽量用；不能结构化的部分保留 blockquote 原文引用
4. **跨课时共享**：本 knowledge 可能服务于多个课时的 generate（在 `applies_to_lessons` 中全部列出）

## 第五步：更新 workspace.yaml

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py update-input \
  "$WORKSPACE_ROOT" knowledge \
  "status=extracted" \
  "source=<教师用书 PDF 绝对路径>" \
  "extracted_md=02_知识点/extracted/<unit>.md"

uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py add-revision \
  "$WORKSPACE_ROOT" \
  "knowledge 提取完成: 教师用书 p.<起始>-<结束>" \
  "02_知识点/extracted/<unit>.md"
```

## 第六步：输出引导块

```markdown
---
## 输入 (2) 知识点 提取完成

📁 `<WORKSPACE_ROOT>/02_知识点/extracted/`
   ├── <title>_教师用书_章节.pdf    截取的独立 PDF (<N> 页)
   ├── pages/page_XXX.png            高 DPI 页面图像
   └── <unit>.md                     结构化知识体系

已更新 workspace.yaml：inputs.knowledge.status = extracted

## 单元服务范围

本次提取的知识点可服务于以下课时：
- <课时 1>
- <课时 2>
...

## 下一步

推荐: 用户核对 knowledge.md 内容 → 如无问题运行 `/aixue-math:generate`（待上线）
或: 继续处理下一单元的教师用书
其他选择:
- `/aixue-math:status`: 查看工作区当前进度
```

## 常见坑

- **页码范围错**：教师用书前面目录/前言多。第一页 Read 后必须核对章节标题
- **分批丢失上下文**：分批处理时，每批 MD 片段必须记录自己覆盖的教参页码和对应课时，防止合成时顺序错乱
- **插图重复描述**：学生教材插图在教师用书中通常只有缩略图 + 简短说明，**不要再次做"画面 + 教学意图"三轨描述**；直接引用 textbook.md 的 fig_pXX_K
- **Markdown 文件锁**：按 CLAUDE.md 规则加 v2/v3 后缀，不报错中断
- **全角标点**：中文内容用半角 `()[]`

## 异常处理

| 情况 | 处理 |
|------|------|
| 未找到 workspace | 报错 `请先运行 /aixue-math:init <课时名>` + exit 1 |
| PDF 路径不存在 | 报错 + exit 1 |
| 页码超出 PDF 范围 | extract_pages.py 会报错，透传 + exit 1 |
| 第一页不是预期单元起始 | 提示用户调整页码，不继续往下 |
| workspace.yaml 已有 knowledge.status = extracted/verified | 警告用户"将覆盖已有提取产物"，等用户确认 |
| 单元超过 60 页 | 超规模提醒用户：是否分拆到多个 workspace？（以免产出 MD 过于冗长） |

## 参考文档

- `references/workspace-schema.md` — workspace.yaml 字段定义（特别是 inputs.knowledge）
- `references/lesson-plan-template.md` — 下游 generate 目标产物结构；knowledge 应服务于它的哪些章节
- `skills/textbook/SKILL.md` — 同源工作流参考（学生教材 → MD）
