---
name: aixue-math:generate
description: >-
  aixue-math 流水线 Stage 3：基于 4 路输入（教材/知识点/写作要求/教案样例）合成结构化教案。
  当用户说「生成教案」「写教案」「aixue-math:generate」「把提取结果合成教案」「产出教案初稿」时触发。
  工作区感知：读 workspace.yaml 的 inputs.* 定位 4 路产物，按 lesson-plan-template.md 的 11 节结构
  产出 Markdown 存入 05_教案/md/，并 upsert workspace.outputs.lessons.<N>。
  支持多课时 workspace（如本单元 1 个输入对应 2 个 40 分钟课时），按 --lessons 参数连续产出。
argument-hint: "[--lessons 1|1,2|all] [--workspace <root>] [--force]"
allowed-tools: Read, Write, Bash, Glob, Grep
version: 0.5.2
---

# aixue-math:generate — 4 路输入 → 结构化教案

> **路径约定**：`{AIXUE_MATH_REF}` = aixue-math 插件 `references/` 目录，`{AIXUE_MATH_SCRIPTS}` = `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/aixue-math/references/lesson-plan-template.md")` 定位，多结果时优先非 `marketplaces/` 路径。

## 为什么这个 skill 存在

`aixue-math:textbook` 解学生教材（课堂看什么、做什么）。
`aixue-math:knowledge` 解教师用书（要教什么、怎么教、防什么坑）。
本 skill 把两者 + 写作要求 + 样例风格合成**真实可上课的教案**。

## 用法

```
/aixue-math:generate [--workspace <root>] [--lessons <spec>] [--force]
```

**参数**：

- `--workspace <root>`：显式指定工作区根；省略时从 cwd 自动发现
- `--lessons <spec>`：
  - 省略 = 询问用户课时划分；
  - `--lessons "1"` = 单课时；
  - `--lessons "1,2"` = 连续产出 2 篇；
  - `--lessons "all"` = 按 workspace 内"课时划分"全量产出
- `--force`：已有 draft 时允许覆盖（默认询问确认）

## 执行流程（六步工作流）

### 第一步：定位工作区 + 加载 4 路输入

```bash
if [ -n "$WORKSPACE_ARG" ]; then
  WORKSPACE_ROOT="$WORKSPACE_ARG"
else
  WORKSPACE_ROOT=$(uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py find-workspace-root "$PWD")
fi
test -f "$WORKSPACE_ROOT/.aixue/workspace.yaml" || exit 1

uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py load-workspace "$WORKSPACE_ROOT"
```

校验 4 路输入就绪：

| 输入 | 必需状态 | 缺失时的行为 |
|------|----------|-------------|
| textbook | `extracted` 或 `verified` | 报错："请先运行 /aixue-math:textbook" |
| knowledge | `extracted` 或 `verified` | 报错："请先运行 /aixue-math:knowledge" |
| guidelines | `ref_only` 或 `customized` | 不阻塞；用 shared 默认即可 |
| samples | `ref_only` 或 `customized` | 不阻塞；用 shared 默认即可 |

若 textbook / knowledge 缺失，**停止**并引导用户补齐。

### 第二步：确定课时划分

若 `--lessons` 未给：

1. 先 Read 教材 md（`inputs.textbook.extracted_md`），统计本输入覆盖的教学节数
2. 若包含多节/多课时（像本项目的"什么是周长"占 p.33-35，实际含 2 个 40 分钟课时），**用 AskUserQuestion 让用户确认拆分**：
   - 选项 A：概念建构｜综合应用（默认推荐）
   - 选项 B：用户自定义（注明每课时覆盖哪些页面段）
3. 将用户选择记录在"本次运行上下文"中（不落盘，属于一次性参数）

若 `--lessons` 已给：直接按拆分产出。

### 第三步：知识点宽松切片

对每个目标课时 N：

1. 读 `inputs.knowledge.extracted_file`（如 `02_知识点/extracted/周长.md`）
2. **宽松切片**构造喂给生成模型的知识点上下文：
   - 全量保留：单元整体定位（核心素养/目标/学情/评价/内容结构）、典型错例、教育新视野
   - 条件保留：各课时要素展开中**仅与本课时匹配的小节**（按标题或 key_concepts 匹配）
   - 剪枝：其他课时的 "教学建议" "学情预判" 等细节段

这样既避免 token 爆炸，又保留宏观素养锚点。

### 第四步：样例风格参考

Read `inputs.samples.source/*.md`（抽取过的 Markdown）前 1/3 部分：
- 主要学习**结构拆分、语言风格、表格列字段**
- **不模仿**样例里的跨版本对比段（本项目 SKIP）
- **不模仿**样例里的具体内容（数据、情境），只模仿**措辞方式**

### 第五步：按 `lesson-plan-template.md` 结构合成教案

读 `{AIXUE_MATH_REF}/lesson-plan-template.md`，按其定义的 **11 节结构**写教案：

```
一、教学内容（基本信息 6 列表）
二、教材分析（课标 + 教参目标 + 编排意图 + 显性/隐性知识 + 知识结构化）
   ❌ SKIP "其他版本教材对比"
三、学情分析（已有基础 + 常见困难 + 前测建议，数据位置占位"待补充"）
四、教学目标（3-4 条，每条后用 【素养表现】标签）
五、教学重点及突破措施（重点 + 3 条）
六、教学难点及突破措施（难点 + 3 条）
七、教学方法与策略（3-4 条方法）
八、资源与工具（教学工具 + 学习资源）
九、学习效果评价（评价题 + 后测数据位置占位"待补充"）
十、教学预设过程（核心！4 列表 + 每环节【环节目标】+【设计意图】）
十一、板书设计（文字版布局 + 占位）
```

**生成顺序建议**：按 `lesson-plan-template.md` "生成顺序建议" 章节执行（先目标/内容，再素养对齐，再教学过程）。

**多课时情况**：对每个课时独立调用本流程，各自形成独立 Markdown。**课时间保持内容不重复**（如课时 2 不再讲授课时 1 已完成的"周长定义"，只调用即可）。

### 第六步：写入 md + 三通道产出（docx + html + pdf）+ 更新 workspace

**aixue-math 默认流程**：每篇教案先产出 md，再同步产出 **docx + html + pdf 三份副本**：

| 格式 | 目录 | 入库 | 定位 |
|------|------|:---:|------|
| **md** | `05_教案/md/`（workspace 内） | ✅ | **源文件**，人读写 |
| **docx** | `<DIST>/05_教案/docx/` | ❌ | 教师打印 / 批注 / 教研组分发 |
| **html** | `<DIST>/05_教案/html/` | ❌ | 图文并茂阅读 / 学校内部分享 / 屏幕浏览 |
| **pdf** | `<DIST>/05_教案/pdf/` | ❌ | 存档 / 统一外观 / 印刷 |

> **源与成品分离（v0.4.0 起）**：只有 md 是源、留在 workspace 内并入 git；docx/html/pdf 是可重建成品，一律落到 `<DIST>` = `workspace.yaml` 的 `dist_dir`（默认 `../../_dist/<课题名>`，即仓库根 `_dist/<课题>/`），**不入 git**。协作者各自本地产出；需要给他人时整包压缩 `_dist/` 传递。
>
> **最新版当面、历史进 OLD**：各格式目录**各只放每课时最新一版**；旧版本由 `rotate-versions` 自动降级到 `<DIST>/05_教案/OLD/{md,docx,html,pdf}/`（历史版同属不入库内容，故统一落在 dist 侧）。没有 draft/final 之分——「当前版 = 根目录里那版」，`workspace.yaml` 用 `current_version` 记版本号。

对每个产出的课时教案 N：

```bash
# 1) md 写入（用 Write 工具）—— 最新版直接写进 05_教案/md/
MD_PATH="$WORKSPACE_ROOT/05_教案/md/v1-课时${N}-${TITLE_SAFE}.md"
# (Write 工具写入 md 内容，含 ![](相对路径) 引用切图)

# 1.5) 解析成品输出根（workspace.yaml 的 dist_dir，默认 ../../_dist/<课题名>）
DIST=$(uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py load-workspace "$WORKSPACE_ROOT" \
       | python -c "import json,sys,os; d=json.load(sys.stdin)['workspace'].get('dist_dir') or '../../_dist/'+os.path.basename('$WORKSPACE_ROOT'); print(d)")
DIST_ABS="$WORKSPACE_ROOT/$DIST"     # dist_dir 是相对 workspace 根的

# 2) 一次产出三格式（docx + html + pdf）→ 落到 DIST/05_教案/{docx,html,pdf}/
#    --output-base 指向成品侧的 05_教案/；省略它会退回「与 md 同级」的旧行为
uv run --script {AIXUE_MATH_SCRIPTS}/generate_all_formats.py "$MD_PATH" \
  --output-base "$DIST_ABS/05_教案"

# 3) 把每课时旧版本降级到 DIST/05_教案/OLD/（各目录每课时只留最新一版）
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py rotate-versions "$WORKSPACE_ROOT"

# 4) upsert workspace（md 路径相对 workspace；成品路径相对 dist_dir）
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py upsert-lesson \
  "$WORKSPACE_ROOT" "$N" \
  "title=${TITLE}" \
  "current_version=1" \
  "md=05_教案/md/v1-课时${N}-${TITLE_SAFE}.md" \
  "docx=\${dist}/05_教案/docx/v1-课时${N}-${TITLE_SAFE}.docx" \
  "html=\${dist}/05_教案/html/v1-课时${N}-${TITLE_SAFE}.html" \
  "pdf=\${dist}/05_教案/pdf/v1-课时${N}-${TITLE_SAFE}.pdf" \
  "generated_at=$(date -Iseconds)"
```

> 成品路径用 `${dist}/` 前缀标记，表示「相对 `workspace.dist_dir` 解析」，与 md 的
> 「相对 workspace 根」区分开 —— 这样 `workspace.yaml` 里一眼能看出哪些产物不在库里。

> 生成第 2、3… 版时，把上面的 `v1` 换成 `v2`/`v3`（写进 `05_教案/md/`），第 3 步 `rotate-versions` 会自动把上一版降级到 `OLD/`。`current_version` 同步改成新版本号。

**脚本依赖**：
- `md_to_docx.py`：Pandoc + mermaid-filter + reference.docx + python-docx 后处理
- `md_to_html.py`：Pandoc → 自包含 HTML（CSS + 客户端 Mermaid + KaTeX）
- `html_to_pdf.py`：Playwright Chromium print-to-pdf（复用 HTML 样式）
- `generate_all_formats.py`：串联以上三者的统一入口
- `crop_figures.py`：按 bbox YAML 配置从教材页面 PNG 裁出单图（教材抽取阶段用）

**关于 docx 产出（目标架构 / 方案 2）**：

完整流水线：
```
md → pandoc (--filter mermaid-filter + --reference-doc)
   → docx (初稿)
   → postprocess_docx.py (表格边框 + 东亚字体提示 + 粗体字体强化)
   → docx (最终)
```

- 使用 `pandoc` + `mermaid-filter` + 自定义 `reference.docx` + `python-docx` 后处理
- 样式（由 `references/lesson-plan-reference.docx` 承载）：
  - 正文：微软雅黑 Microsoft YaHei 10.5pt 行距 1.5
  - 标题：微软雅黑 Bold 黑色（取消 pandoc 默认蓝色）
  - 代码块：Consolas 9.5pt
  - 表格：Table 样式含全边框 + postprocess 为每个 cell 补 tcBorders
- **结构图必须使用 Mermaid**（见下方"禁止 ASCII 艺术字"规则）
- 不阻塞 md 产出：若 pandoc/mermaid-filter/python-docx 失败，打印警告后继续
- 目录结构固化为 `05_教案/{md,docx,html,pdf}/` 四个格式目录（最新版），历史进 `05_教案/OLD/{md,docx,html,pdf}/`
- **没有 draft/final 状态**：当前版 = 根目录里那版，版本号记在 `workspace.yaml` 的 `current_version`；不存在「定稿」这个独立动作或目录
- 样式定制源：`scripts/build_reference_doc.py` 改样式 → 重跑 → 更新 reference.docx

**依赖（首次运行需安装）**：
- `pandoc` 3.x
- `npm install -g mermaid-filter @mermaid-js/mermaid-cli`
- Python：python-docx（uv 自动管理）

### 禁止 ASCII 艺术字结构图（硬约束）

知识结构化图、板书分区图等视觉结构化内容，**必须使用以下之一**：

1. **Mermaid `flowchart`**（推荐，自动编译为 PNG 嵌入 docx）：
   ```mermaid
   flowchart TD
       A["封闭图形"] --> B["直线边界"]
       A --> C["曲线边界"]
       B --> D["一周的长度"]
       C --> D
   ```

2. **Markdown 表格**（适合 2-3 列布局的板书分区说明）

**禁止**用 `┌─┐│└┘▼` 等 ASCII 艺术字在代码块中画图——在 Word 中因中英文宽度不齐会完全错位，用户看不清。

最后追加一条 revision：

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py add-revision \
  "$WORKSPACE_ROOT" \
  "aixue-math:generate 产出 ${COUNT} 篇教案: 课时${LIST}" \
  "05_教案/md/v1-课时1-xxx.md,05_教案/md/v1-课时2-yyy.md"
```

### 第七步：输出引导块

```markdown
---
## 教案生成完成（v1 草稿）

产出文件：
- 📝 05_教案/md/v1-课时1-<title>.md
- 📝 05_教案/md/v1-课时2-<title>.md

工作区状态：
- outputs.lessons.1.current_version = 1
- outputs.lessons.2.current_version = 1

## 下一步

推荐: 用户审阅教案 → /aixue-math:refine 做局部调整（产出 v2，旧版自动进 OLD/）
其他选择:
- /aixue-math:status 看整体进度
- 直接编辑 draft 文件后手动 upsert-lesson 改 version
```

## 教案 Markdown 的 frontmatter 约定

每份产出的教案文件必须有如下 frontmatter：

```yaml
---
lesson_workspace: 周长_什么是周长        # workspace.name
lesson_num: 1                           # 本课时在 workspace 中的序号
lesson_title: 什么是周长·认识与测量        # 课时标题
grade: 三年级下册
subject: 数学
textbook_edition: 北师大版
unit: 第三单元 周长
duration_minutes: 40
lesson_type: 新授课
course_scope: "教材 p.33 + p.34 生活中其他物体的周长"
input_refs:
  textbook: 01_教材/extracted/什么是周长.md
  knowledge: 02_知识点/extracted/周长.md
  guidelines: shared/03_写作要求/writing-guidelines.md
  samples:
    - shared/04_教案样例/extracted/一米有多长.md
    - shared/04_教案样例/extracted/公顷平方千米.md
generated_at: <ISO8601>
version: 1
generator: aixue-math:generate v0.1.0
---
```

## 生成时的硬约束（清单）

- [ ] **不出现** "其他版本教材对比" 章节
- [ ] 总共 11 节，编号使用中文数字"一、二、..."
- [ ] 教学目标 3-4 条，**每条末尾附核心素养标签**（如 `【几何直观 / 量感】`）
- [ ] 教学过程用 4 列表：教学环节 / 学生活动及预设 / 教师调控 / 评价观测点
- [ ] 每个教学环节有 `【环节目标】` 开头 + `设计意图：...` 结尾
- [ ] 学生预设 **至少 2 条**（一条正常 + 一条典型错误/不同思路）
- [ ] 课时总时长 = 40 分钟，各环节时间分配给出具体数字
- [ ] 不伪造前测/后测数据，用 `> 📊 **待教师补充**：...` 占位
- [ ] 板书设计用文字版布局 + 占位说明
- [ ] 使用**半角标点**和 LaTeX 公式
- [ ] 作业设计总量 ≤ 15 分钟

## 常见坑

- **token 爆炸**：4 路输入全量拼接可能超上下文。使用"宽松切片"严格挑选相关段落
- **样例内容被照抄**：只模仿样例的**结构与措辞**，不复用样例里的具体情境/数据
- **多课时内容重叠**：同一 workspace 的多篇教案若共享同一教材内容，需要明确**课时 N 只教 N 段**，前序内容用"复习导入"方式带过
- **不规范的 fig 引用**：课件中引用教材插图时，必须使用 textbook.md 中定义的 `fig_pXX_K` 锚点

## 异常处理

| 情况 | 处理 |
|------|------|
| textbook/knowledge 未 extracted | 报错引导用户跑对应 skill |
| 05_教案/md/ 下文件已存在且非 --force | 询问确认覆盖，或自动 bump 到 v2/v3 |
| Windows 文件锁（教师正打开 draft）| 按 CLAUDE.md 规则加 v2/v3 后缀保存，不报错中断 |
| 4 路输入有 2 路以上 status=pending | 报错并列出哪些缺 |

## 参考文档

- `{AIXUE_MATH_REF}/lesson-plan-template.md` — 产物结构规约（11 节字段定义 + SKIP 清单）
- `{AIXUE_MATH_REF}/workspace-schema.md` — workspace.yaml schema（特别是 outputs.lessons）
- `shared/03_写作要求/writing-guidelines.md` — 项目级写作理念与风格规范
- `shared/04_教案样例/extracted/*.md` — 样例参考
- `skills/knowledge/SKILL.md` — 前序阶段（知识点抽取）
- `skills/textbook/SKILL.md` — 前序阶段（教材抽取）
