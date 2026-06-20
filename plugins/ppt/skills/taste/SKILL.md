---
name: ppt:taste
description: >-
  视觉评审 PPT, 输出双轴评分 (layout / palette 解耦) + 描述性建议 + actionable 改进项.
  双模式 (锚点模式 / 通用原则模式): 锚点模式基于 ppt plugin 共享锚点库 (10 张华为 golden
  锚点 + 5 条审美原则 + 5 类反模式) 做视觉对照; 通用原则模式仅按 P1-P5 原则 + AP1-AP5
  反模式打分, 适用于 codex 等非华为风产物.
  当用户提到 "评审 PPT" "ppt:taste" "看一下 deck 质量" "审美评分" "找问题" 时触发.
argument-hint: "<pptx 路径> 或 <png 目录> [--mode anchor|general]"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
version: 3.0.6
---

# PPT:Taste — 视觉评审

视觉评审 .pptx 或 PNG 目录, 输出 markdown 报告. **核心设计: 双轴评分 (layout / palette 解耦)**, 引用 plugin 共享锚点库做视觉对照.

## 路径约定

`<plugin-root>` 指 ppt plugin 根目录. 推导方式: Base directory 是 `<plugin-root>/skills/taste/`, 取两级父目录即为 `<plugin-root>`. 后续 `<plugin-root>` 替换为实际路径.

## 设计基础: 双轴评分 (硬约束)

按 anchors.yaml 原则 P2 "布局结构 vs 调性配色 解耦": 不能合并 layout 和 palette 成单一 "美感分". 必须分两轴独立评分.

- **layout_score (1-5)**: 仅评布局结构
  - 对齐 / 框比例 / 视觉重量 / 关联表达 / 留白节奏 / 字号节奏
  - 参考: 10 张 golden 锚点的 layout
- **palette_score (1-5)**: 仅评调性配色
  - 底色 / 强调色 / 装饰元素 / 整体调性
  - 参考: 原则 P1 "浅色调优先" + 反模式 AP1 (黑色满底) / AP2 (红色满底)

**为什么分两轴**: 用户审美核心发现——很多 deck "布局可参考但底色需洗白". 单轴评分会把这种 deck 评中等, 双轴评分会清晰显示 "layout 4, palette 1" 让用户精准定位问题.

## 评分标尺锚定 (避免分数通胀)

| 分数 | 含义 |
|---|---|
| 5 | 真正出色, 达到 golden 锚点水平 (10 张华为官方主打胶片) |
| 4 | 满足专业标准的合格水平, 但尚未到 golden |
| 3 | 有明显问题但可用 |
| 2 | 多个问题, 需重做 |
| 1 | 严重缺陷 (命中反模式 AP1-AP5) |

**关键**: 评 4 之前问自己 "这页真的接近 golden 锚点吗?" 避免默认 5 分.

## 评分模式选择

两种评分模式, 双轴解耦与 1-5 标尺在两种模式下都成立, 区别在**评分依据**:

- **anchor (锚点模式, 默认)**: golden 锚点视觉对照 + P1-P5 + AP1-AP5. 适用 huawei renderer 产物及任何希望对标华为 golden 水准的 deck.
- **general (通用原则模式)**: 仅按 anchors.yaml 的 P1-P5 原则 + AP1-AP5 反模式打分, 不做 golden 对照. 适用 codex 等非华为风格产物 — 不以 "像不像华为" 论分.

模式判定优先级 (从高到低):

0. **锚点可用性前置 (marketplace 安装场景)**: 先 Glob `<plugin-root>/anchors/golden/*.png`. 若 anchors.yaml 或 golden PNG **缺失** (publisher 发布到公共 marketplace 时排除了华为锚点资产 SEC-001/002), 则**强制 general 模式**, 评分依据用本 SKILL.md「内置审美原则」节 (不依赖 anchors.yaml). 即使用户传 `--mode anchor` 也降级, 并在报告与对话各提示一句『锚点库未随发布提供, 已按通用原则模式评审』. 开发环境 (cc-dev / 本地 plugin) 锚点齐全, 此条不触发.
1. 用户显式 `--mode anchor|general`
2. 已知产物来源: 检查 deck 同目录 `.ppt-workdir/runs/*-codex/manifest.json`, 仅当某 manifest 的 `pptx_path` 指向目标 deck (路径归一化后一致) 时 → general; 其余情况 (无 -codex run 目录, 或 manifest 指向别的 deck — 如 `--compare` 后双引擎产物共存同一目录) → anchor. 不能只看 "-codex run 目录是否存在", 双引擎共存目录会误判 renderer 产物
3. 默认 anchor

## 参数解析

从 `$ARGUMENTS` 解析:
- **路径** (必需): `.pptx` 文件 或 PNG 目录 (含 slide-NN.png)
- `--mode anchor|general` (可选): 评分模式, 缺省按「评分模式选择」节判定

示例:
- `/ppt:taste output/report.pptx` — 输入 PPTX, skill 内部转 PNG
- `/ppt:taste output/.ppt-workdir/png/` — 输入 PNG 目录, 直接评
- `/ppt:taste output/codex-deck.pptx --mode general` — 通用原则模式评审

## 执行流程

### Step 1: 输入识别 + PNG 准备

判断输入类型:

- **`.pptx` 文件**: 用 LibreOffice 转 PDF, 再用 PyMuPDF 转 PNG
  ```bash
  TMP=<deck-stem>.ppt-workdir-taste
  mkdir -p "$TMP"
  soffice --headless --convert-to pdf --outdir "$TMP" "<pptx-path>"
  # 然后 PyMuPDF 转 PNG (一行 Python 脚本, dpi=96)
  ```
  PPTX 转 PNG 不依赖 ppt:create 工具链, 独立运行
- **PNG 目录**: 直接进 Step 2

### Step 2: 加载锚点库 (锚点模式必做)

> **前置**: 若「评分模式选择」第 0 条判定锚点缺失 (marketplace 安装), 跳过本 Step, 走「通用原则模式规程」的 Step 2 (general 替代) + 内置审美原则.

执行前用 Read 加载以下文件到当前会话:

1. **`<plugin-root>/anchors.yaml`** (锚点库索引)
   - 5 条审美原则 (P1-P5)
   - 5 类反模式 (AP1-AP5)
   - 103 锚点 metadata (golden 10 + layout-only 23 + extended 70)

2. **`<plugin-root>/anchors/golden/` 全部 10 张 PNG** (视觉参考):
   ```
   Glob: <plugin-root>/anchors/golden/*.png
   Read 全部 10 张
   ```
   这 10 张是用户从 211 张华为胶片中重选的高质量参考, 评每张目标 slide 时**主动用这 10 张做视觉对照**.

3. **layout-only / extended** 默认**不 Read PNG**, 仅从 anchors.yaml 读文字描述. 评审中如遇特定 deck 类型 (如 channel / wifi6 商务调) 需要补充参考, 按需 Read `<plugin-root>/anchors/layout-only/<deck_id>/*.png`.

### Step 3: 逐页评审

对每张 slide PNG (用 Read 加载):

1. **识别 slide type**: cover / toc / section / content / data / closing / slogan
2. **找对应 golden 锚点比对**:
   - cover → wifi7-p001
   - content → banking-p004 / p021 / p026
   - data → datacenter-p003 / p005
   - closing → banking-p043
   - 未明确分类的 golden (banking-p021/p026/datacenter-p005/wifi7-p004/p019/p094) 作为通用 content / data 参考
3. **双轴评分**:
   - layout_score (1-5) + 1-2 句具体观察 (对齐 / 留白 / 视觉重量等)
   - palette_score (1-5) + 1-2 句具体观察 (底色 / 强调色 / 调性)
4. **反模式检查**: 对照 AP1-AP5 标明命中项 (若有)
5. **改进建议** (仅当任一轴 ≤ 3 时): actionable 1-2 句, 引用具体 golden 锚点 (如 "改为浅色底, 参考 wifi7-p001 的自然摄影调性")

### Step 4: 输出 markdown 报告

落到 `<deck-stem>.taste-report.md`, 跟输入 deck 同目录. 格式:

```markdown
# ppt:taste 评审报告

- **Deck**: <name>
- **Timestamp**: <ISO 8601>
- **Pages**: <N>
- **Mode**: anchor | general-principles
- **Anchor library version**: 2.0 (plugin scope)

## Deck 总分

| 维度 | 平均 | 最高 | 最低 |
|---|---|---|---|
| Layout | x.xx | x | x |
| Palette | x.xx | x | x |

**综合判断** (2-3 句): {基于双轴平均给出整体定位}

## 逐页评分

| # | Type | Layout | Palette | 观察 | 反模式 |
|---|---|---|---|---|---|
| 1 | cover | 4 | 4 | ... | — |
| 2 | toc | 3 | 2 | 装饰字过大 + 黑底 | AP3 |
| ... |

## 命中反模式汇总

| 页 | AP | 描述 | 修复方向 |
|---|---|---|---|
| 2 | AP3 | 巨型装饰字 | 标题字号缩到正文 3 倍以内 |
| 4 | AP1 | 黑色满底 | 改浅色底 (参考 wifi7-p001) |
| ... |

## 改进项 (按优先级)

1. **{slide-N} {核心问题}**: {具体修复方向, 引用 golden 锚点}
2. ...

## 锚点参考来源

本评审使用以下 golden 锚点作为视觉对照:
- {列出实际用到的 golden 文件}
```

(general 模式下「锚点参考来源」节替换为: `## 评分依据` + 一行 `anchors.yaml P1-P5 + AP1-AP5`)

### Step 5: 输出确认

完成报告后:
1. 输出报告路径让用户打开
2. 简短总结 deck 级别 layout / palette 双轴分数 + Top 3 改进项
3. 询问用户是否需要对某些页深入分析 / 或对建议提问

## 内置审美原则 (锚点缺失 fallback)

发布到公共 marketplace 的 ppt 不含 anchors.yaml / anchors 资产 (华为内部胶片, publisher SEC-001/002 排除). 此时 general 模式用下列内置 P1-P5 + AP1-AP5 评分 (与 anchors.yaml 的 principles/antipatterns 同源, 仅去除含锚点 ID 的 evidence):

**审美原则 (P1-P5)**:
- **P1 浅色调优先** (palette, 权重高): 整体调性优先浅色 / 白底 / 浅蓝渐变. 避免: 黑色满底 / 红色满底 / 深蓝商务调 / 棕黑装饰底.
- **P2 布局结构 vs 调性配色 解耦** (权重 critical): 布局/结构与调色/底色是独立维度, 必须分两轴评 (layout_score / palette_score).
- **P3 字号节制 + 内容舒展** (layout, 权重高): 标题中等大 (不超过正文 3 倍), 正文字大且有留白, 数据数字用红色加粗作焦点, 装饰字 (目录/01/02 编号) 不应巨大.
- **P4 框间关联可视化** (layout, 权重中): 多对象不能堆罗列, 必须有视觉化关联——漏斗 (流动) / 箭头 (因果转换) / 比喻图 (作锚) / 结构化标签 (场景/模型/工程/平台).
- **P5 数据严谨** (权重中): 所有数据页底部必有来源标注 (Gartner / 公司年报 / URL).

**反模式 (AP1-AP5, 命中即对应轴 ≤ 2)**:
- **AP1 黑色/深色满底章节分隔**: 整页黑底/深底 + 巨号红/黄/白装饰字作章节分隔 (除战略煽情口号外不应用).
- **AP2 红色满底**: 整页红色满底 (如谢谢页/封底).
- **AP3 巨型装饰字**: '目录' / '01' / '03' / 巨号谢谢 等装饰字超过正文 4 倍, 占画面 1/3 以上.
- **AP4 内容稀疏 + 巨字补位**: 一页只有 3-4 个词 + 配巨号字, 信息密度过低.
- **AP5 模板变量字面值渲染**: code='X' / title='Y' / summary='Z' 这种 Python-like 变量定义直接出现在 PPT 内容层.

## 通用原则模式规程 (--mode general)

general 模式复用上述执行流程骨架 (Step 1 PNG 准备 / Step 4 报告 / Step 5 确认不变), 仅替换 Step 2 与 Step 3:

### Step 2 (general 替代): 加载评分依据

优先 Read `<plugin-root>/anchors.yaml` 的 principles 节 (P1-P5) + antipatterns 节 (AP1-AP5). **若 anchors.yaml 缺失** (marketplace 安装, publisher 已排除锚点资产) → 直接用本 SKILL.md「内置审美原则 (锚点缺失 fallback)」节的 P1-P5 + AP1-AP5, 不报错. **不 Read golden PNG** — 省 token, 且不以 "像不像华为" 论分. layout-only / extended 同样不加载.

### Step 3 (general 替代): 逐页评审

对每张 slide PNG (用 Read 加载):

1. **识别 slide type**: cover / toc / section / content / data / closing / slogan
2. **逐条原则观察**: 每页按 P1 (浅色调) / P3 (字号节制 + 内容舒展) / P4 (框间关联可视化) / P5 (数据严谨) 逐条给出具体观察; P2 (解耦) 体现为双轴评分本身, 不单独打分
3. **反模式检查**: 对照 AP1-AP5 标明命中项 (若有)
4. **双轴评分** (标尺语义平移):
   - 5 = P1/P3/P4/P5 全满足且无任何 AP 命中, 布局有编辑级叙事感
   - 4 = 满足专业标准的合格水平
   - 3 及以下与锚点模式标尺含义相同
   - **命中 AP 任一, 对应轴自动 ≤ 2**
5. **改进建议** (仅当任一轴 ≤ 3 时): actionable 1-2 句, **引用原则编号** (如 "P1: 改浅色底" / "P3: 标题字号缩到正文 3 倍以内"), 不引用 golden 文件名

## 注意事项

1. **双轴严格解耦**: layout_score 和 palette_score **绝对不能合并**. 不要写综合美感分.
2. **分数标尺锚定**: 5 分 = 真正出色 (golden 水平), 4 分以下都是有问题. 不要默认 5 分通胀.
3. **反模式优先**: 命中 AP1-AP5 任一, 对应轴自动 ≤ 2.
4. **layout-only 锚点的使用**: 评 channel / wifi6 类深色 deck 时主动 Read `anchors/layout-only/<deck_id>/*.png` 作为布局补充参考, 但**只学 layout 不学 palette**.
5. **extended 仅文字**: 不要主动 Read extended/ 下 PNG (token 成本高), 仅查 anchors.yaml 描述.
6. **textual rendering bug 检测**: 看到 `code='X' title='Y' summary='Z'` 类 Python 字面值要立即标 AP5 (模板变量泄露).
7. **避免空泛形容词**: 禁止 "整洁现代" / "克制有力" 这种泛词. 必须给具体观察 (字号几号 / 底色什么 / 哪里对齐失衡).
8. **general 模式公平性**: general 模式禁止因 "不像华为风格" 扣分, 只按 P1-P5 原则与 AP1-AP5 反模式打分. 非华为风的高品位设计 (编辑级排版 / 摄影感视觉) 满足原则即可得高分.

## 输出位置

`<deck-stem>.taste-report.md` 跟输入 deck 同目录.

输入是 PPTX → 报告落到 `.taste-report.md` (替换 `.pptx`)  
输入是 PNG 目录 → 报告落到 PNG 目录的父目录 (用户期望与 deck 同级)
