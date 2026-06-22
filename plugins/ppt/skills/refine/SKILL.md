---
name: ppt:refine
description: >-
  对 ppt:create 已生成的 PPT 做自然语言追加调整 (必须有 .ppt-workdir/slide-plan.yaml).
  当用户提到"调整 PPT""修改 PPT""ppt:refine""PPT 微调"时触发.
argument-hint: "<pptx 路径> <调整指令>"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 3.0.7
---

# PPT:Refine — 自然语言追加调整

## v3.4.0 简化说明 + 适用范围明示

**仅支持有 `<pptx目录>/.ppt-workdir/slide-plan.yaml` 的 deck** (即 ppt:create 生成的). 外部 PPTX (没有 slide-plan.yaml 的) **不支持** — v3.3.x 文档承诺"用 python-pptx 逆向分析推断 visual_type"实际从未实现, LLM 现场写逆向解析逻辑也不可靠. 外部 PPTX 请用 `/ppt:create` 重新生成.

v3.4.0 同时删除 Agent-V 和 Agent-R LLM 自审 (无 ground truth, 增加 token 成本不增加质量), 改为 deterministic 校验 (`validate_plan.py`) + 可选 `/ppt:taste` 评审.

## 路径约定

`<plugin-root>` = skills/refine/ 的两级父目录. 执行 bash 前替换实际路径.

## 参数解析

从 `$ARGUMENTS` 中解析:
- **PPTX 文件路径** (必需): 要调整的 .pptx 文件
- **调整指令** (必需): 自然语言描述的修改需求

示例: `/ppt:refine output/report.pptx 第3页换成左图右文布局, 标题改为行动标题`

## 执行流程

### Step 0: 前置检查

```bash
# 必须存在
test -f <pptx目录>/.ppt-workdir/slide-plan.yaml || { echo "未找到 slide-plan.yaml. ppt:refine 仅支持 ppt:create 生成的 deck. 外部 PPTX 请用 /ppt:create 重新生成"; exit 1; }
```

未通过此检查时, 立即 AskUserQuestion 给用户:
- 选项 1: "用 /ppt:create 重新生成" (推荐)
- 选项 2: "我手动改 PPTX 即可"

### Step 1: 解析指令 + 用户确认

1. Read .pptx 关联的 slide-plan.yaml 和 .theme-prompt.md (若存在)
2. Read `<plugin-root>/design-guide.md` + `<plugin-root>/anchors.yaml` (审美锚点 metadata)
3. 理解自然语言指令, 映射为 slide-plan.yaml 的具体修改:
   - 识别目标 slide (页码 / 标题 / 内容匹配)
   - 识别修改类型 (布局变更 / 内容修改 / 样式调整)
   - 生成修改方案
4. **AskUserQuestion 确认理解**:
   - 选项 1: "确认修改方案"
   - 选项 2: "需要调整" (用户补充说明)

### Step 2: 修改 slide-plan.yaml

如修改涉及 visual_type 变更或新加 slide, **先**重装载主题决策框架:
```bash
uv run --script <plugin-root>/engine/prompt_assembler.py --theme <theme-from-plan-meta> --output <workdir>/.theme-prompt.md
```

Read .theme-prompt.md 确保 visual_type 选择遵循当前主题的硬约束 + 软引导, 避免破坏 huawei 应用率门禁.

**仅文字 / 数据 / 字号微调** (不改 visual_type, 不加 slide) 时可跳过.

修改 slide-plan.yaml 中受影响的 slides, 写回原路径.

### Step 3: 局部重渲染 + deterministic 校验

```bash
uv run python <plugin-root>/engine/render.py <workdir>/slide-plan.yaml \
    --theme <theme> --output <output-path> \
    --base-pptx <original-pptx> --only-slides <changed-slide-ids>
```

**注意**: `--only-slides` 当前实现是"追加新版本到末尾", 不是原位置替换. 用户需要确认目标页号语义. 如需原位置替换, 重渲染全部 slides 不传 `--base-pptx`.

渲染后跑 deterministic 校验 (带 `--theme` 让应用率门禁不退化):
```bash
uv run --script <plugin-root>/engine/validate_plan.py <workdir>/slide-plan.yaml --theme <theme> --json
```

检查受影响 slides 的 FAIL / WARN (含反模式 / 连续相同 visual_type) 和 `theme_application.status` 不退化为 FAIL (exit 2). 退化时 → 回到 Step 2 按 `.theme-prompt.md` 软引导改回 huawei 专属版式.

### Step 4: 完成

输出:
```
PPT 已更新: <output-path>
修改了 N 页 (页码: x, y, z)
评审 (可选): /ppt:taste <output-path>
继续调整: /ppt:refine <output-path> <新指令>
```
