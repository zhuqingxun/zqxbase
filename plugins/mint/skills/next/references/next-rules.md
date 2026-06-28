# next-rules.md — mint:next 决策树规则集（v1 纯规则推理）

本文件描述 mint:next 引导推荐的规则集。规则分两层，由不同组件实现：

- **核心流水线规则**（单会议 Rule 1-4、全景 Rule 5a/5b）：由 `meta_io.compute_next_hints()`（单会议）与 `meta_io.workspace_overall_recommendation()`（全景）实现。这部分本文件与 Python 实现**互为契约，二者须保持一致**。
- **维护类规则**（Rule 6a/6b/6c/7/8）：**不在** `compute_next_hints()` 职责内，由 `revise` / `patch` / `sync` 三个 SKILL 在「最后一步：更新元数据并输出引导块」段**手工覆盖** `meta.yaml.next_hints` 实现。本文件对这部分仅作行为说明，**实际命令文案以各 SKILL 的覆盖段为准**。

> 历史说明：本文件早期声明「规则文本为 source of truth，Python 实现跟进」，但维护类规则从未进入 `compute_next_hints()`，实际由 SKILL 层覆盖。该绝对声明已撤销，改为上述分层契约描述（见 todo `fix-mint-next-rules-doc-code-drift`）。

## 原则

- v1 纯规则推理，禁止调用 LLM
- 规则按优先级从高到低顺序尝试，命中即返回
- `scenario` 字段预留不读（本 PRD 明确非目标）
- 每条规则返回形如 `{primary: {cmd, reason}, alternatives: [{cmd, when}]}` 的结构

## 单会议规则（作用于 meta.yaml）

### Rule 1：blockers 优先

- **条件**：`current.blockers.length > 0`
- **推荐**：
  - `primary.cmd` = 源头 skill（ambiguity / missing_input → `/mint:refine <meeting_dir>`；其他 → 对应 source skill）
  - `primary.reason` = 形如 `当前有 {N} 个阻塞项待处理: {第一条 description 摘要}`
- **alternatives**：
  - `{cmd: /mint:status --detail, when: 查看全部 blocker 详情}`

### Rule 2：pending 阶段推进

- **条件**：存在 `stages.*.status == pending`
- **判定顺序**：`transcribe → refine → polish → extract` 取第一个 pending 阶段
- **跳过逻辑**：若目标阶段名在 `intent.skip_stages` 中，继续取下一个阶段
- **推荐**：
  - `primary.cmd` = `/mint:<stage> <meeting_dir>`
  - `primary.reason` = 形如 `{上一阶段} 已完成，建议继续 {目标阶段}`（若为 transcribe 则 `尚未转录，先将音频转为文字`）
- **alternatives**：
  - 若跳过 polish → `{cmd: /mint:extract --source clean, when: 跳过 polish 直接结构化}`
  - 若处于 refine 之后 → `{cmd: /mint:patch <词>, when: 发现 ASR 错字需修正}`
  - 通用兜底：`{cmd: /mint:status, when: 先查看详细进度}`

### Rule 3：全部 completed 但 deliverables 未对齐

- **条件**：所有 `stages.*.status == completed` 且 `intent.deliverables` 中有项在 extract 产物中缺失
- **推荐**：
  - `primary.cmd` = `/mint:revise <meeting_dir>` 或 `/mint:extract <meeting_dir>`（视缺失类型）
  - `primary.reason` = 形如 `交付物 {xxx} 尚未产出，建议补齐`
- **alternatives**：
  - `{cmd: /mint:status --detail, when: 核对产物清单}`

### Rule 4：全部 completed 且对齐

- **条件**：所有 stages completed 且 deliverables 齐全
- **推荐**：
  - `primary.cmd` = 空或提示收尾（本 PRD 不做 archive，仅文字提示）
  - `primary.reason` = `当前会议已完成全部产出，可进入下一会议或归档`
- **alternatives**：
  - `{cmd: /mint:next --all, when: 查看其他会议状态}`
  - `{cmd: /mint:status --detail, when: 最终产物核查}`

## 维护类规则（revise / patch / sync）

> ⚠️ **以下 Rule 6a/6b/6c/7/8 由对应 SKILL 末尾「最后一步：更新元数据并输出引导块 → 返回主流水线语义覆盖」段手工覆盖 `next_hints` 实现，不在 `compute_next_hints()` 内**。要改这些行为，请改对应 SKILL（`skills/revise|patch|sync/SKILL.md`），而非 `meta_io.py`。下文是行为契约说明，命令文案须与 SKILL 覆盖段保持一致。触发判断以 SKILL 当前依据为准：revise 按 `--from` 阶段，patch/sync 因在自身执行末尾覆盖、"最近动作"天然即该操作。（按 `revisions[].affected_files` 路径匹配是未来若把这些规则改入 `compute_next_hints()` 规则引擎时的设计预案，依赖 `add-revision --files` 写入真实路径，当前 SKILL 覆盖**不读** affected_files。）

### Rule 6a：revise 修改校对稿（--from 校对稿/refine）

- **触发**：revise 的 `--from` 为校对稿（refine 阶段）
- **primary.cmd**：`/mint:polish <meeting_dir>`
- **primary.reason**：`下游编辑稿需重新生成以反映修订`
- **alternatives**：`/mint:extract <meeting_dir>`、`/mint:status`

### Rule 6b：revise 修改编辑稿（--from 编辑稿/polish）

- **触发**：revise 的 `--from` 为编辑稿（polish 阶段）
- **primary.cmd**：`/mint:extract <meeting_dir>`
- **primary.reason**：`下游分析稿需刷新`
- **alternatives**：`/mint:status`

### Rule 6c：revise 修改分析稿（--from 分析稿/extract）

- **触发**：revise 的 `--from` 为分析稿（extract 阶段）
- **primary.cmd**：`/mint:status`
- **primary.reason**：`分析稿无下游，建议查看最终产出`
- **alternatives**：`/mint:next`、`/mint:patch`

### Rule 7：patch 完成

- **触发**：最近动作为 patch
- **primary.cmd**：`/mint:status <meeting_dir>`
- **primary.reason**：`验证稿件已刷新，查看状态快照`
- **alternatives**：`/mint:refine <meeting_dir>`（校对质量下降需重跑）、`/mint:next`

### Rule 8：sync 完成

- **触发**：最近动作为 sync
- **primary.cmd**：`/mint:status <meeting_dir>`
- **primary.reason**：`查看同步后的最终产出状态`
- **alternatives**：`/mint:patch`（同步含术语/人名修正建议沉淀词表）、`/mint:next`

## 全景规则（多会议，作用于 workspace-view）

### Rule 5a：多会议优先级排序

工作区全景模式下，整体推荐按以下键（降序）选 top-1：

1. `blockers_count > 0`（有阻塞优先）
2. 进度落后程度（completed stages 数量少者优先；用 `cursor` 与流水线顺序推导）
3. 距 `last_action` 时间越久优先（`None` 视为最小）
4. `active` 标记（resolved_by=cwd 或 last_action 的 active 会议优先）

输出结构：

```
primary:
  cmd: "/mint:next <dir>"  # 指向推荐的会议
  reason: "优先处理 {dir}: {主因，如 "2 个阻塞项待处理" / "最久未操作" / "进度落后"}"
alternatives:
  - {cmd: "/mint:status --workspace --detail", when: "查看全部会议详情"}
```

### Rule 5b：interview 全部 polish 完成 → 跨会议汇总

由 `workspace_overall_recommendation()` 实现，**优先级高于 Rule 5a**（命中即返回，不再走优先级排序）。

- **触发**：`workspace.scenario == "interview"` 且全部会议 `progress_num >= 3`（polish 及之前已完成）且会议数 > 0
- **未生成汇总时**（`汇总分析/mint_*.md` 不存在）：
  - `primary.cmd` = `/mint:summarize`
  - `primary.reason` = `全部访谈已完成 polish，建议生成跨会议汇总`
  - `alternatives` = `{cmd: /mint:status --workspace --detail, when: 先核查各会议最终产物}`
- **已生成汇总时**：
  - `primary.cmd` = 空（提示可直接消费 `汇总分析/` 下的 `mint_*.md`）
  - `alternatives` = `{cmd: /mint:status --workspace --detail, when: 核查各会议质量}`、`{cmd: /mint:summarize, when: 重新生成（旧产物自动备份到 汇总分析/old/）}`
- **`workspace` 为 None**：跳过本规则，退化为 Rule 5a（向后兼容）

> 注：代码注释中本规则历史上称「Rule 6」，与维护类 Rule 6a/6b 编号撞车，已统一更名为 Rule 5b（归属全景规则，与 Rule 5a 同层）。

## Rule 2 skip_stages 边界示例

- `intent.skip_stages = ["polish"]` 且当前 refine 已 completed → 取 extract（跳过 polish 到再下一个）
- `intent.skip_stages = ["polish", "extract"]` 且 refine 已 completed → 视为全部完成，进入 Rule 4
