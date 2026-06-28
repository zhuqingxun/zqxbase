# scenario-presets.md — 场景枚举与 deliverables 预设

本文件是 `mint:init` AskUserQuestion 三问的选项来源，同时也是 meta_io.init_workspace 过滤 deliverables 的依据。

> **机器单一源**：deliverables 的可选并集（Q2）与各场景默认集的**权威定义在 `scripts/meta_io.py`**
> （`DELIVERABLE_SELECTABLE` / `DELIVERABLE_PRESETS`），经 `meta_io.py deliverable-presets` CLI 对外暴露。
> 本文档为该 CLI 输出的人类可读说明；两者一致性由 `tests/mint-types/test_deliverable_presets.py` 守卫，
> 改动预设时**先改 meta_io.py 常量**，本文档随之同步。

## Scenario 枚举

- interview: 主题访谈（有提纲+受访人）
- meeting: 一次性多人交流

仅这两种合法值，其他值由 mint:init 拒绝、mint:next 宽容但不消费。

## Deliverables 预设

### interview
- 观点分析
- 行动项
- 精华语录
- 要点摘要

### meeting
- 决议清单
- 行动项
- 问题清单
- 要点摘要

## AskUserQuestion Q2 选项并集策略

AskUserQuestion schema 限制 options 最多 4 项，且单次 batch 无法根据 Q1 条件渲染。

Q2 展示给用户的 options 为两场景并集的 4 项子集：

- 观点分析
- 行动项
- 决议清单
- 要点摘要

（精华语录、问题清单因 options 上限无法放入 Q2，由 init 写入时自动补齐）

## init 写入 workspace.yaml 的过滤规则

用户在 Q2 勾选完成后，`meta_io.init_workspace` 按 Q1 scenario 过滤并补齐：

- scenario = interview：
  - 从用户选择中 **删除** `决议清单`（非本场景产物）
  - 若 `精华语录` 未出现，**自动补齐**到末尾
  - 结果示例：用户选 `[观点分析, 行动项, 决议清单]` → 写入 `[观点分析, 行动项, 精华语录]`

- scenario = meeting：
  - 从用户选择中 **删除** `观点分析`
  - 若 `问题清单` 未出现，**自动补齐**到末尾
  - 结果示例：用户选 `[观点分析, 决议清单, 行动项, 要点摘要]` → 写入 `[决议清单, 行动项, 要点摘要, 问题清单]`

过滤后 `deliverables` 顺序保持用户勾选顺序，自动补齐项追加到末尾。

## PRD 断言映射

- INIT-01：interview + `[观点分析, 行动项]` → 写入 deliverables 包含 `观点分析` 和 `行动项`
- INIT-02：meeting + 默认全选（含 `观点分析`）→ 写入 deliverables 必须含 `决议清单` 且不含 `观点分析`

## Q3 goal 4 预设

AskUserQuestion schema 不支持纯文本输入，Q3 采用 4 预设 + 自动 Other 兜底策略（详见 init/SKILL.md）：

1. 输出综合洞察报告
2. 留存结构化记录
3. 撰写专题分析
4. 一次性事项纪要

用户选择预设 → 存 label；用户选自动 Other → 存其填写文本。
