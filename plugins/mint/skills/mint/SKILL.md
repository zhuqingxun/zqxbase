---
name: mint
description: >-
  MINT (Meeting Intelligence) 一键流水线——从音频到结构化智能输出。
  默认执行全部四个阶段：Transcribe -> Refine -> Polish -> Extract，阶段间设门禁供用户审阅。
  当用户提到"处理录音""从头跑一遍""mint""完整处理"时触发。
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill
version: 2.1.2
---

# MINT 一键流水线编排器

从音频到结构化输出的全流程编排，阶段间设门禁供用户审阅决策。

## 用法

```
/mint <音频文件路径> <人名或会议名> [参数]
```

### 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--skip-polish` | 跳过 Polish 阶段 | 不跳过 |
| `--from <stage>` | 从指定阶段开始（transcribe/refine/polish/extract） | transcribe |
| `--mode <conservative\|moderate>` | Refine 模式 | moderate |
| `--脱敏` | 在 Refine 和 Polish 阶段同时生成脱敏版本 | 不脱敏 |

## 流水线拓扑

```
Transcribe → Refine ──┬──→ Polish → Extract（默认路径）
                       │
                       └──→ Extract（--skip-polish 路径）
```

## 工作目录结构

编排器会在音频文件所在目录（或用户指定位置）创建标准工作目录：

```
{会议名}/
├── 01_音频/           ← 原始音频
├── 02_原始稿/             ← Stage 1: ASR 转录
│   ├── {name}_原始稿.md
│   └── old/
├── 03_校对稿/           ← Stage 2: 清洁逐字稿
│   ├── {name}_校对稿.md
│   ├── {脱敏名}_校对稿_脱敏.md    ← 脱敏版本（--脱敏 时生成）
│   └── old/
├── 04_编辑稿/        ← Stage 3: 编辑稿（可选）
│   ├── {name}_编辑稿.md
│   ├── {脱敏名}_编辑稿_脱敏.md    ← 脱敏版本（--脱敏 时生成）
│   ├── {name}_结构化分析.md
│   ├── {脱敏名}_结构化分析_脱敏.md ← 脱敏版本（--脱敏 时生成）
│   ├── {name}_精华原声.md
│   └── old/
├── 05_分析稿/         ← Stage 4: 结构化输出
│   ├── 要点摘要.md
│   ├── 发言人分析.md
│   ├── 行动项.md
│   ├── 决策与遗留.md
│   └── old/
└── meta.yaml
```

> **命名约定**：`{name}` = 受访者/会议真实名称；`{脱敏名}` = 脱敏代号（如 `受访者_01`），由全局注册表（工作目录上级的 `desensitization_registry.yaml`）统一分配，确保跨项目唯一。各项目 `meta.yaml` 的 `desensitization.name_map` 存储本项目的映射副本。

## 编排流程

### 1. 参数解析与初始化

1. 解析用户输入，提取：音频路径、会议名、可选参数
2. 确定工作目录路径。如果目录已存在，Read `meta.yaml` 获取当前状态
3. 如果是全新项目，创建目录结构和初始 `meta.yaml`
4. 如果指定了 `--from`，从 meta.yaml 确认前置阶段已完成，否则提示用户

### 2. 阶段执行与门禁

对每个阶段，执行「调用 -> 摘要 -> 门禁」三步循环：

---

#### Stage 1: Transcribe（`--from transcribe` 或默认起点）

**调用**：使用 Skill 工具调用 mint:transcribe，传入音频路径和会议名

**摘要展示**：
```
## Transcribe 完成

- 音频时长：XX 分钟
- 转录字数：XXXX 字
- 识别说话人：N 位
- 输出文件：02_原始稿/{name}_原始稿.md
```

**门禁 1**：通过 AskUserQuestion 提供选项：
- "继续 Refine 阶段" — 进入下一阶段
- "重新转录（调整参数）" — 让用户指定新参数后重跑
- "停止，我手动处理" — 结束流水线

---

#### Stage 2: Refine（`--from refine`）

**调用**：使用 Skill 工具调用 mint:refine，传入工作目录和 mode 参数。如果指定了 `--脱敏`，同时传递给 refine

**摘要展示**：
```
## Refine 完成

- 模式：moderate
- 修正项数：XX 处
- 质量评分：忠实度 XX / 流畅度 XX / 一致性 XX / 清洁度 XX / 格式 XX
- 输出文件：03_校对稿/{name}_校对稿.md
- 脱敏版本：03_校对稿/{脱敏名}_校对稿_脱敏.md（如指定 --脱敏）
```

**门禁 2**：通过 AskUserQuestion 提供选项：
- "继续 Polish 阶段"（如果未 --skip-polish）/ "继续 Extract 阶段"（如果 --skip-polish）
- "重新 Refine（换模式/模型）" — 让用户指定新参数后重跑
- "停止，我手动处理"

如果 `--脱敏` 且生成了脱敏版本，在进入 Polish 门禁时让用户选择输入源："使用原版校对稿" / "使用脱敏校对稿"

---

#### Stage 3: Polish（跳过条件：`--skip-polish`）

**调用**：使用 Skill 工具调用 mint:polish，传入工作目录。如果指定了 `--脱敏`，同时传递给 polish

**摘要展示**：
```
## Polish 完成

- 编辑稿字数：XXXX 字
- 提取语录：XX 条
- 结构化段落：XX 个
- 输出文件：
  - 04_编辑稿/{name}_编辑稿.md
  - 04_编辑稿/{name}_结构化分析.md
  - 04_编辑稿/{name}_精华原声.md
- 脱敏版本（如指定 --脱敏）：
  - 04_编辑稿/{脱敏名}_编辑稿_脱敏.md
  - 04_编辑稿/{脱敏名}_结构化分析_脱敏.md
```

**门禁 3**：通过 AskUserQuestion 提供选项：
- "继续 Extract 阶段"
- "重新 Polish（调整参数）"
- "停止，我手动处理"

---

#### Stage 4: Extract（`--from extract`）

**调用**：使用 Skill 工具调用 mint:extract，传入工作目录

**来源选择逻辑**：
- 如果 `04_编辑稿/` 目录存在且有内容 → source = "polished"
- 否则 → source = "clean"
- 如果选定的输入源目录下存在脱敏版本文件，通过 AskUserQuestion 让用户选择："使用原版" / "使用脱敏版"

**摘要展示**：
```
## Extract 完成

- 来源：clean / polished 稿
- 输出文件：
  - 05_分析稿/要点摘要.md — 会议摘要
  - 05_分析稿/发言人分析.md — 发言人档案
  - 05_分析稿/行动项.md — 行动项
  - 05_分析稿/决策与遗留.md — 决策记录
```

**门禁 4**（最终确认）：通过 AskUserQuestion 提供选项：
- "全部完成，结束" — 展示最终产出物清单并结束
- "重新 Extract（调整参数）"
- "回到某个阶段重跑" — 询问具体回退到哪个阶段

---

### 3. 最终产出物清单

所有阶段完成后，展示完整产出物清单：

```
## MINT 流水线完成：{会议名}

### 产出物
| 文件 | 说明 |
|------|------|
| 02_原始稿/{name}_原始稿.md | ASR 原始转录 |
| 03_校对稿/{name}_校对稿.md | 清洁逐字稿 |
| 03_校对稿/{脱敏名}_校对稿_脱敏.md | 脱敏版清洁逐字稿（--脱敏） |
| 04_编辑稿/{name}_编辑稿.md | 编辑稿 |
| 04_编辑稿/{脱敏名}_编辑稿_脱敏.md | 脱敏版编辑稿（--脱敏） |
| 04_编辑稿/{name}_结构化分析.md | 结构化分析 |
| 04_编辑稿/{脱敏名}_结构化分析_脱敏.md | 脱敏版结构化分析（--脱敏） |
| 04_编辑稿/{name}_精华原声.md | 语录集 |
| 05_分析稿/要点摘要.md | 会议摘要 |
| 05_分析稿/发言人分析.md | 发言人档案 |
| 05_分析稿/行动项.md | 行动项 |
| 05_分析稿/决策与遗留.md | 决策记录 |

提示：使用 /mint:status 查看处理状态，/mint:patch 修正错字，/mint:revise 修订内容。
```

## meta.yaml 管理

编排器负责维护 `meta.yaml` 的生命周期：

### 初始化（新项目）

```yaml
project: "{会议名}"
created: {当天日期}
source_audio: "{音频文件名}"

stages:
  transcribe:
    status: pending
  refine:
    status: pending
    desensitized: false
  polish:
    status: pending
    desensitized: false
  extract:
    status: pending

revisions: []

desensitization:      # --脱敏 时由 refine 阶段填充
  name_map: {}        # 如 {张三: 受访者_01}
```

### 阶段完成时更新

每个子 skill 执行完毕后，编排器更新对应阶段的状态：

```yaml
stages:
  {stage}:
    status: completed
    version: {版本号，重跑则递增}
    completed_at: {ISO 时间戳}
    params: {本次运行参数}
    quality: {质量评分，仅 refine 阶段}
```

### 重跑阶段

重跑某阶段时：
1. 将该阶段现有产出物移入对应的 `old/` 子目录（按版本号命名）
2. 重置该阶段及所有下游阶段的 status 为 pending，但已有产出物保留在 `old/` 目录中供参考
3. 版本号递增

## 边界规则

- **编排器不实现阶段逻辑**：每个阶段的具体实现在对应子 skill 中，编排器只负责调用和门禁
- **门禁不可跳过**：每个阶段完成后必须经用户确认才能继续，这是质量控制的关键环节
- **meta.yaml 是唯一状态源**：所有阶段状态、版本、参数都以 meta.yaml 为准
- **`--from` 需要前置条件**：从中间阶段开始时，编排器必须验证前置阶段已完成
- **重跑会重置下游**：重跑某阶段时，该阶段之后的所有阶段状态回退为 pending
- **错误恢复**：如果某阶段执行失败，meta.yaml 中该阶段 status 设为 failed，用户可选择重试或手动处理
