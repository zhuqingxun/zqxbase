---
name: ppt:taste
description: >-
  视觉评审 PPT, 输出双轴评分 (layout / palette 解耦) + 描述性建议 + actionable 改进项.
  基于 ppt plugin 共享锚点库 (10 张华为 golden 锚点 + 5 条审美原则 + 5 类反模式).
  当用户提到 "评审 PPT" "ppt:taste" "看一下 deck 质量" "审美评分" "找问题" 时触发.
argument-hint: "<pptx 路径> 或 <png 目录>"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
version: 3.0.4
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

## 参数解析

从 `$ARGUMENTS` 解析:
- **路径** (必需): `.pptx` 文件 或 PNG 目录 (含 slide-NN.png)

示例:
- `/ppt:taste output/report.pptx` — 输入 PPTX, skill 内部转 PNG
- `/ppt:taste output/.ppt-workdir/png/` — 输入 PNG 目录, 直接评

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

### Step 2: 加载锚点库 (必做)

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

### Step 5: 输出确认

完成报告后:
1. 输出报告路径让用户打开
2. 简短总结 deck 级别 layout / palette 双轴分数 + Top 3 改进项
3. 询问用户是否需要对某些页深入分析 / 或对建议提问

## 注意事项

1. **双轴严格解耦**: layout_score 和 palette_score **绝对不能合并**. 不要写综合美感分.
2. **分数标尺锚定**: 5 分 = 真正出色 (golden 水平), 4 分以下都是有问题. 不要默认 5 分通胀.
3. **反模式优先**: 命中 AP1-AP5 任一, 对应轴自动 ≤ 2.
4. **layout-only 锚点的使用**: 评 channel / wifi6 类深色 deck 时主动 Read `anchors/layout-only/<deck_id>/*.png` 作为布局补充参考, 但**只学 layout 不学 palette**.
5. **extended 仅文字**: 不要主动 Read extended/ 下 PNG (token 成本高), 仅查 anchors.yaml 描述.
6. **textual rendering bug 检测**: 看到 `code='X' title='Y' summary='Z'` 类 Python 字面值要立即标 AP5 (模板变量泄露).
7. **避免空泛形容词**: 禁止 "整洁现代" / "克制有力" 这种泛词. 必须给具体观察 (字号几号 / 底色什么 / 哪里对齐失衡).

## 输出位置

`<deck-stem>.taste-report.md` 跟输入 deck 同目录.

输入是 PPTX → 报告落到 `.taste-report.md` (替换 `.pptx`)  
输入是 PNG 目录 → 报告落到 PNG 目录的父目录 (用户期望与 deck 同级)
