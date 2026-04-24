---
name: ppt:refine
description: >-
  对已有 PPT 进行自然语言追加调整。支持有/无 slide-plan.yaml 两种情况。
  当用户提到"调整 PPT""修改 PPT""ppt:refine""PPT 微调"时触发。
  也适用于: 用户指定了 .pptx 文件并描述了修改需求的场景。
argument-hint: "<pptx 路径> <调整指令>"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
version: 3.0.2
---

# PPT:Refine — 自然语言追加调整

对已有 .pptx 文件进行自然语言描述的调整。单次指令模式。

## 路径约定

本文档中 `<plugin-root>` 指 plugin 根目录。推导方式：Base directory 的两级父目录（即 `skills/refine/` 的上两层）。执行 bash 命令前，先确定实际路径再替换 `<plugin-root>`。

## 设计参考

执行任何修改前，读取 `<plugin-root>/design-guide.md` 了解设计哲学和反模式清单。在分析现有 PPTX 结构时，对照反模式清单标记已有问题。如果用户指令涉及布局调整，推荐符合设计指南的 visual_type。

## 参数解析

从 `$ARGUMENTS` 中解析：
- **PPTX 文件路径**（必需）：要调整的 .pptx 文件
- **调整指令**（必需）：自然语言描述的修改需求

示例：`/ppt:refine output/report.pptx 第3页换成左图右文布局，标题改为行动标题`

## 执行流程

### Step 1: 解析指令

1. 读取指定的 .pptx 文件
2. 检查是否存在关联的 `slide-plan.yaml`：
   - 查找路径：`<pptx所在目录>/.ppt-workdir/slide-plan.yaml`
   - **有 slide-plan.yaml** → 直接修改 plan
   - **无**（外部 PPTX）→ 使用 python-pptx 分析 PPTX 结构，生成等价 slide-plan.yaml

3. 理解自然语言指令，映射为 slide-plan.yaml 的具体修改：
   - 识别目标 slide（页码/标题/内容匹配）
   - 识别修改类型（布局变更/内容修改/样式调整）
   - 生成修改方案

4. 向用户确认理解是否正确

### Step 2: 局部重规划

1. 修改 slide-plan.yaml 中受影响的 slides
2. **作为审查 Agent-V** 检查修改后一致性（维度和阈值同 ppt:create Stage 3）
3. 产出 updated slide-plan.yaml

### Step 3: 局部重渲染

1. 仅重渲染变更的 slides：
```bash
uv run python <plugin-root>/engine/render.py <workdir>/slide-plan.yaml \
    --theme <theme> --output <output-path> \
    --base-pptx <original-pptx> --only-slides <changed-slide-ids>
```
2. 运行渲染后校验：
```bash
uv run --script <plugin-root>/engine/validate_plan.py <workdir>/slide-plan.yaml --json
```
   检查受影响 slides 的 FAIL 和 WARN（包括反模式警告，如修改是否导致连续相同 visual_type）
3. **作为审查 Agent-R** 质检（维度和阈值同 ppt:create Stage 4 的 QA 验证循环）
4. 产出 refined .pptx

### 完成

输出：
```
PPT 已更新: <output-path>
修改了 N 页 (页码: x, y, z)
如需继续调整，使用 /ppt:refine <output-path> <新指令>
```

## 外部 PPTX 逆向分析

对于没有 slide-plan.yaml 的外部 PPTX，使用以下方法生成等价 plan：

1. 用 python-pptx 遍历所有 slide：
   - 提取每页形状列表（类型、位置、尺寸、文本内容）
   - 推断 visual type（基于形状数量和布局模式）
   - 提取配色和字体信息
2. 构造 slide-plan.yaml 并保存到 `<pptx目录>/.ppt-workdir/`
