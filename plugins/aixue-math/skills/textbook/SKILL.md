---
name: aixue-math:textbook
description: >-
  aixue-math 流水线 Stage 1：处理输入 (1) 教材。从教材 PDF 按页码范围提取章节并生成带「图像教学意图」
  的结构化 Markdown，作为教案生成的第一路输入。当用户说「提取教材」「处理教材 PDF」「aixue-math:textbook」
  「把课本 49-55 页转成 Markdown」「教材结构化」时触发。工作区感知：自动写入 01_教材/extracted/ 并
  更新 workspace.yaml 的 inputs.textbook 状态。与普通 PDF OCR 不同，核心价值是保留每张插图的教学意图
  （这张图为什么出现在这里、想让学生理解什么），而不是只抽取文字。
argument-hint: "<PDF 路径> <起始页> <结束页> [--workspace <root>]"
allowed-tools: Read, Write, Bash, Glob, Grep
version: 0.5.2
---

# aixue-math:textbook — 教材 PDF → 结构化 Markdown

> **路径约定**：`{AIXUE_MATH_SCRIPTS}` = aixue-math 插件 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/aixue-math/scripts/workspace_io.py")` 定位，多结果时优先非 `marketplaces/` 路径。

## 为什么这个 skill 存在

普通 PDF 提取工具（pypdf、marker、MinerU 等）处理教材时丢失了最宝贵的信息——**插图的教学意图**。小学/中学教材的每张插图都是教学脚手架：

- 实物照片（树叶、数学书）帮学生建立生活直觉
- 情境图（小公园、动物园）让抽象概念具象化
- 对话气泡引导学生自己归纳公式
- 方格纸图训练数格子的操作技能

下游教案生成（aixue-math:generate）如果只看到"这里有张图"，无法基于图设计教学活动；只有理解"这张图在教什么"，AI 才能写出贴合教材设计意图的教案。

本 skill 的核心做法：**把 Claude 自己的视觉理解能力当 VLM 用**，逐页分析并产出"画面 + 教学意图 + 可延展活动"三轨标注的 Markdown。

## 用法

```
/aixue-math:textbook <PDF 路径> <起始页> <结束页> [--workspace <root>]
```

**必需参数**：

- `<PDF 路径>` 教材 PDF 绝对路径
- `<起始页>` PDF 物理页（从 1 开始，包含）
- `<结束页>` PDF 物理页（包含）

**可选参数**：

- `--workspace <root>` 显式指定工作区根；省略时从 cwd 自动发现

**不要自己猜页码范围**。如果用户没说清楚，直接请用户告知起止页。书本页码和 PDF 物理页码经常差 3-10 页（前言/目录）。

## 执行流程

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

调用 bundled 脚本 `scripts/extract_pages.py`，产物直接写入 `01_教材/extracted/`：

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/extract_pages.py \
  --pdf "<PDF 路径>" \
  --start <起始页> --end <结束页> \
  --output-dir "$WORKSPACE_ROOT/01_教材/extracted" \
  --chapter-name "<workspace.name>" \
  --dpi 400
```

`<workspace.name>` 从 `workspace.yaml` 的 `workspace.name` 字段读取。脚本会：

1. 用 PyMuPDF 从原 PDF 截取指定页范围为独立子 PDF（`<name>_章节.pdf`）
2. 每页渲染为 400 DPI PNG 保存至 `pages/page_XXX.png`
3. 创建 `assets/` 空目录（预留供后续精准切图使用）

产物目录结构：

```
01_教材/extracted/
├── <name>_章节.pdf             截取出的独立 PDF
├── pages/page_XXX.png          每页高 DPI PNG
└── assets/                     预留目录
```

### 第三步：视觉核对 + 逐页分析

**第一动作**：Read `01_教材/extracted/pages/` 下第一页，**确认这是不是预期的章节**。书本页码和 PDF 物理页码经常不一致，截取范围如果错了，调整后重跑第二步。不要盲目继续。

确认范围正确后，依次（或并行）Read 所有页面。**你自己就是 VLM**，不需要调用外部 API。对每一页完整提取：

1. **文字内容**：完整转录所有可见文字，保留层级（章节标题、小节标题、题号、对话气泡内的话、页码）。
2. **每张插图**：分配稳定 ID（格式 `fig_p{PDF物理页码}_{序号}`），记录：
   - **画面**：客观描述看到什么——颜色、构图、标注的数字/文字、人物动作、物体名称。下游 LLM 读到这段要能「看到」图。不要只写"这里有一张图"。
   - **教学意图**：这张图为什么在这里、想让学生理解什么、对应教材哪个教学目标。**这是本 skill 最值钱的信息**。
   - **可延展的课堂活动**（可选但强烈推荐）：基于这张图可以设计的互动、操作、讨论。教案作者会直接复用这部分。
3. **公式**：LaTeX（`$...$` 或 `$$...$$`）。
4. **表格**：Markdown 表格。
5. **教材栏目**：保留"想一想""试一试""练一练""做一做""认一认"等原文栏目名，用 `🔶` 或 `●` 等符号强调。

### 第四步：产出结构化 Markdown

最终产出 `01_教材/extracted/<workspace.title>.md`（若 title 为空用 name）。遵循以下五条核心设计原则：

1. **Frontmatter 全局元数据**：来源 PDF、页码映射、章节结构、关键概念、教学方法。让下游 LLM 不打开原 PDF 也能理解内容范围。Frontmatter 应至少包含：
   ```yaml
   source_pdf: <原 PDF 文件名>
   pdf_pages: "<起始>-<结束>"
   book_pages: "<书本起始>-<书本结束>"
   chapter_title: <章节名>
   grade: <年级>
   textbook_edition: <教材版本>
   extracted_at: <YYYY-MM-DD>
   ```
2. **图像标注内联展开**：不要用 `[[FIGURE: xxx]]` 跳转占位符，在原文位置直接用 blockquote 展开描述。下游 LLM 顺序读取时上下文才连贯。
3. **保留教材栏目**：教材的栏目名（"试一试"、"练一练"等）是教学设计的骨架，用原文 + 视觉符号保留。
4. **全章纵览总结**：文末补一节"教学重点 / 难点 / 核心数学思想 / 推荐的教学资源准备"，方便直接喂给 aixue-math:generate。
5. **来源页码可追溯**：每个小节开头标注 `### PDF p.XX / 书本 p.YY`，并在小节开头给出 `pages/page_XXX.png` 引用路径。

### 第五步：更新 workspace.yaml

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py update-input \
  "$WORKSPACE_ROOT" textbook \
  "status=extracted" \
  "source_pdf=<PDF 绝对路径>" \
  "pdf_pages=<起始>-<结束>" \
  "book_pages=<书本起始>-<书本结束>" \
  "extracted_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "extracted_md=<相对 workspace 根的路径，如 01_教材/extracted/什么是周长.md>"
```

同时追加一条 revision：

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py add-revision \
  "$WORKSPACE_ROOT" \
  "textbook 提取完成: PDF p.<起始>-<结束>" \
  "01_教材/extracted/<title>.md,01_教材/extracted/<name>_章节.pdf"
```

### 第六步：输出引导块

```markdown
---
## 输入 (1) 教材 提取完成

📁 `<WORKSPACE_ROOT>/01_教材/extracted/`
   ├── <name>_章节.pdf           截取的独立 PDF（<N> 页）
   ├── pages/page_XXX.png        高 DPI 页面图像
   └── <title>.md                 结构化 Markdown（带三轨图像标注）

已更新 workspace.yaml：inputs.textbook.status = extracted

## 数据核对

本次提取基于视觉读数，部分数字可能需要用户对照原 PDF 核对，详见 Markdown 文末"需人工确认的数据点"清单。

## 下一步

推荐: `/aixue-math:knowledge` (输入 2 — 知识点提取)
或: 用户核对 textbook 数据 → 如无问题，调 `/aixue-math:verify textbook` 把 status 推进到 verified
其他选择:
- `/aixue-math:status`: 查看工作区当前进度
- `/aixue-math:next`: 智能下一步引导
```

## 图像标注范式（必读）

三段标注的分工决定了下游可用性：

- **画面** 写给"看不到图的下游读者"（包括下游 LLM）——要让 ta 能脑补还原图
- **教学意图** 写给"要二次加工这份内容的人"（教案生成器、备课老师）——要让 ta 知道这图能利用到什么教学目标
- **可延展的课堂活动** 是直接可用的教学素材，减少下游从零构思的负担

黄金范例（实物情境图）：

> **[fig_p49_1] 实物图组：一片绿色树叶 + 一本数学书封面**
> **画面**：树叶为单片心形绿叶，脉络清晰；数学书封面为蓝底，有"数学"二字及小朋友看书插画。
> **教学意图**：选用学生日常熟悉的实物，把"周长"从抽象概念落地到可观察、可触摸的对象。引导学生通过"用彩笔沿边线描一圈"的动作感知"一周"的完整性与封闭性。
> **可延展的课堂活动**：让学生找身边其他物体（课本、作业本、橡皮、书桌面）进行描边，并用自己的话描述"一圈"的意义。

## 数据准确性与不确定处理

教材中经常出现**单位混合**（厘米 + 毫米）、**故意留空**（让学生填）、**视觉小字**等设计。视觉读数有时会错位或模糊，此时：

1. 读不清的数字标注 `[读数不确定]` 或 `（具体数值以原图为准）`
2. 在最终 Markdown 文末开一节"需人工确认的数据点"列核对清单给用户
3. **不要猜具体数字**——宁可标注不确定，也不让教案作者基于错误数据设计教学

### 多边形边数核对（重要）

彩色情境图（公园俯视图、动物园、菜地等）中的不规则多边形，在视觉上**极易把一条边误数为两条**。约束做法：

1. **数"带数字标签的边"而非"图形轮廓"**：每条边一定有明确的数值标签贴在边旁，数标签而不是数轮廓线段。
2. **求和自检**：把读到的边长加起来，如果教材上下文给出参考答案（如整数周长 1600 米等），用求和对比验证；和对不上就回去重数。
3. **跨版本反向验证**：同一情境在不同版本（如三上 vs 三下）的教材重复出现时，可用已有成品的边长和来反查当前读数。
4. **拐角处单独确认**：对每个拐角逐一确认"这是拐点还是中间折线"。

## 常见坑

- **书本页码 ≠ PDF 物理页**：PDF 前面通常有封面、扉页、目录若干页。Step 3 渲染后先 Read 第一页 PNG 确认章节匹配——不一致就微调页范围重跑。
- **不要自动切出单张插图**：bbox 切图精度差会失真。整页 PNG 保留在 `pages/` 下，下游需要原图时直接查看整页。除非用户明确要求切图，否则不做。
- **Windows 文件锁**：生成 Markdown 时，若输出路径被其他程序（VS Code、浏览器）锁定，按 CLAUDE.md 规则加 v2/v3 后缀保存，不要报错中断。
- **全角标点**：Markdown 中的中文内容使用半角 `()[]` 替代全角 `（）【】`，避免某些渲染器乱码。

## 异常处理

| 情况 | 处理 |
|------|------|
| 未找到 workspace | 报错 `请先运行 /aixue-math:init <课时名>` + exit 1 |
| PDF 路径不存在 | 报错 + exit 1 |
| 页码超出 PDF 范围 | extract_pages.py 会报错，透传 + exit 1 |
| 第一页视觉核对失败（非预期章节） | 提示用户调整页码范围后重跑，不继续往下 |
| workspace.yaml 已有 textbook.status = extracted/verified | 警告用户"将覆盖已有提取产物"，等用户确认 |

## 参考文档

- `references/workspace-schema.md` — workspace.yaml 字段定义（特别是 inputs.textbook）
