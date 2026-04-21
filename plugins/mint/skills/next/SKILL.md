---
name: mint:next
description: >-
  MINT 智能引导——基于元数据和当前位置，推荐最优下一步动作。支持单会议聚焦 / 工作区全景 / 强制全景三种模式。
  当用户提到"下一步""接下来做什么""next""引导""我该做啥""接什么"时触发。
  也适用于：用户跑完某个阶段想确认下一动作、多会议并行时想看全景推荐、卡在某处想看其他路径。
allowed-tools: Read, Bash, Glob, Grep
version: 2.1.5
---

# mint:next — 智能引导

> **路径约定**：`{MINT_REF}` = mint 插件 `references/` 目录，`{MINT_SCRIPTS}` = 同级 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/mint/references/next-rules.md")` 定位，多结果时优先非 `marketplaces/` 路径。

基于 `meta.yaml` + `.mint/workspace.yaml` 的元数据和当前 cwd，通过纯规则推理给出下一步推荐。不调用 LLM，输出稳定可预期。

## 用法

```
/mint:next                  # 默认：基于 cwd 推断 active 或走全景
/mint:next <meeting_name>   # 显式聚焦某会议
/mint:next --all            # 强制全景模式
```

- `<meeting_name>`：会议子目录名（相对于工作区根），如 `02_屈卓`
- `--all`：无视 cwd，强制输出工作区全景

## 核心职责区分

- **mint:next**：决策推荐（基于规则引擎推导推荐命令）
- **mint:status**：状态快照（质量评分 / 产物清单 / blocker 详述）

两者互补，禁止重叠输出。

## 执行流程

### 第一步：解析参数

从 `$ARGUMENTS` 提取：
- 显式 `meeting_name`（首个非 `--` 开头的位置参数）
- `--all` 标志

### 第二步：定位工作区根（前置检查）

调用 meta_io 的 `find-workspace-root` 子命令，传入当前工作目录：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py find-workspace-root "$(pwd)"
```

- **exit 0**：stdout 为工作区根绝对路径
- **exit 1**：工作区未初始化，立即输出错误并停止：

```
错误：当前目录不在任何 mint 工作区内（未找到 .mint/workspace.yaml）。

请先运行 /mint:init 初始化工作区，或切换到已初始化的工作区目录后重试。
```

**关键**：错误消息必须含关键词 `未初始化` 和 `mint:init`（对应 PRD NEG-01 断言）。exit 非 0。

### 第三步：active 推断

按以下优先级确定 active 会议或决定全景模式。记录 `resolved_by` 字段供全景模式输出使用。

| 优先级 | 条件 | 结果 |
|--------|------|------|
| 1 | 参数传入 `--all` | 全景模式，`resolved_by = explicit` |
| 2 | 参数传入 `meeting_name` | active = meeting_name，`resolved_by = explicit` |
| 3 | cwd 下存在 `meta.yaml`（即 cwd 本身是会议目录） | active = cwd basename，`resolved_by = cwd` |
| 4 | cwd == 工作区根 | 全景模式，`resolved_by = cwd` |
| 5 | 其他（cwd 在工作区内但非会议目录） | 扫所有会议，取 `last_action` 最晚者作为 active，`resolved_by = last_action` |

**优先级 5 的兜底逻辑**：调 `scan-meetings` 按 `last_action` 字典序降序（ISO 8601 字符串即时间序），取首个；若 `last_action` 全为空，则退化为全景模式。

### 第四步：加载数据

#### active 模式

1. 拼接 active 路径：`<workspace_root>/<meeting_name>`
2. 校验 meta.yaml 存在且字段完整：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py validate-meta "<active_dir>"
```

exit 2 时输出错误消息（消息已由 meta_io.py 提供，含"缺少必要字段"关键词）并停止。

3. 计算 next_hints 并同时扫全景（供尾部附表用）：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py compute-next-hints "<active_dir>" --workspace "<workspace_root>"
uv run --script {MINT_SCRIPTS}/meta_io.py scan-meetings "<workspace_root>"
```

`compute-next-hints` 写回 meta.yaml 的 `next_hints` 字段，stdout 输出 JSON `{primary: {cmd, reason}, alternatives: [{cmd, when}]}`。

4. 读取 active 会议的 meta.yaml（通过 Read 工具）获取 `current.cursor`、`current.blockers` 用于后续输出。

#### 全景模式

1. 扫描全部会议：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py scan-meetings "<workspace_root>"
```

stdout 为 JSON 数组，每项含 `dir / project / cursor / progress / progress_num / last_action / blockers_count`。

2. 读取 `.mint/workspace.yaml`：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py load-workspace "<workspace_root>"
```

stdout 为 JSON，含 `workspace.name / workspace.scenario / intent.goal / intent.deliverables`。

3. 整体推荐通过 `workspace-recommendation` CLI 一次调用完成（内部 scan + load workspace + Rule 5/6）：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py workspace-recommendation "<workspace_root>"
```

stdout 为 JSON `{primary: {cmd, reason}, alternatives: [{cmd, when}]}`。

> **Rule 6 触发**：CLI 内部自动判定；当 `workspace.scenario == "interview"` 且所有会议 `progress_num >= 3`（polish 及之前完成）时——若 `<workspace>/汇总分析/mint_*.md` 不存在则推荐 `/mint:summarize`；若已存在则提示"已完成"，alternatives 给重跑或核查质量。其他情况走 Rule 5（多会议优先级 top-1）。
>
> **备选实现**：历史 Python 内联脚本调 `workspace_overall_recommendation(meetings, workspace)` 等价，但新 CLI 更简洁且保证 workspace 参数传递正确。

### 第五步：输出格式化

#### active 模式输出

按以下模板输出（注意全部使用半角标点）：

```markdown
## active: {meeting_name} (cursor: {current.cursor})

推荐下一步: {primary.cmd}
原因: {primary.reason}

其他选择:
{alternatives 循环展开，每行 "- {cmd}: {when}"；空数组输出 "- 无"}

阻塞项: {current.blockers.length 为 0 时输出 "无"；否则输出 "{N} 项（详见 /mint:status --detail）"}

---
## 工作区全景

| 会议 | cursor | 进度 | 阻塞 |
|------|--------|------|------|
| {每个 meeting 一行，active 会议在 dir 列加 "(active)" 标识} |
```

**关键约束**：
- 尾部附表仅 4 列（简短），不含 last_action / quality（避免与 status 重叠）
- `{alternatives 循环展开}`：Read `{MINT_REF}/next-hints-template.md` 参考展开风格——每行 `- {cmd}: {when}`，空数组输出单行 `- 无`

#### 全景模式输出

```markdown
## 工作区: {workspace.name}

场景: {workspace.scenario}
项目目标: {intent.goal}

| 会议 | cursor | 进度 | 阻塞 | last_action |
|------|--------|------|------|-------------|
| {每个 meeting 一行} |

---
整体推荐: {overall.primary.cmd}
理由: {overall.primary.reason}

其他选择:
{overall.alternatives 循环展开}
```

**关键约束**：
- 全景模式**不输出** active 聚焦段（对应 PRD NEXT-03 断言）
- 列顺序：`会议 | cursor | 进度 | 阻塞 | last_action`
- 会议列值直接用 `dir` 字段
- 进度列显示 `scan-meetings` 返回的 `progress` 字符串（如 `2/4`）；已完成 4/4 可追加 ✓
- `last_action` 缺失时显示 `-`

## 规则引擎说明

规则详见 `{MINT_REF}/next-rules.md`。本 skill 不重复规则实现，全部委托 `meta_io.compute_next_hints()` 和 `meta_io.workspace_overall_recommendation()`。

规则摘要（供用户理解输出）：
- Rule 1：有 blockers 优先推荐处理
- Rule 2：取下一个 pending 阶段推进（respect `intent.skip_stages`）
- Rule 3：全部 completed 但 deliverables 未对齐 → 推荐 revise/extract 补齐
- Rule 4：全部完成且对齐 → 提示收尾
- Rule 5：全景模式按 blockers_count > 0 → progress_num 升序 → last_action 升序 排序
- Rule 6：工作区全景模式下，scenario == "interview" 且所有会议 progress_num >= 3（polish 及之前完成）→ 若 `<workspace>/汇总分析/mint_*.md` 不存在则推荐 `/mint:summarize` 生成跨会议汇总；已存在则提示"已完成"，alternatives 给 `/mint:status --workspace --detail` 与重跑 `/mint:summarize`。scenario=meeting 或任一会议 polish 未完成时不触发

## 边界规则

- **只读 + 一次 compute_next_hints 写入**：skill 自身不修改 meta.yaml 的 stages/revisions 等字段；`compute-next-hints` 仅写入 `next_hints` 字段
- **scenario 只存不读**：规则引擎不依赖 scenario 字段（PRD 9.7 非目标）
- **禁用 LLM**：推理全由 `meta_io.py` 规则树完成，本 skill 不做语义推断
- **空工作区处理**：工作区存在但无任何会议时，全景模式输出"工作区暂无会议，先运行 /mint:transcribe"
- **active 会议缺 meta.yaml**：显式参数指向不存在的会议，输出错误 `会议 {name} 不存在或缺少 meta.yaml` 并退出
- **性能基线**：20 会议全景 < 1000ms（scan-meetings 单次 IO）

## 异常处理

| 情况 | 处理 |
|------|------|
| `find-workspace-root` exit 1 | 输出 NEG-01 错误消息（含"未初始化"和"mint:init"），exit 非 0 |
| `validate-meta` exit 2 | 透传错误消息（已含"缺少必要字段"），exit 非 0 |
| 显式 meeting_name 指向不存在目录 | 输出"会议 {name} 不存在或缺少 meta.yaml"，exit 非 0 |
| scan-meetings 返回空数组且要全景模式 | 输出"工作区暂无会议"提示 |
| `compute-next-hints` 返回 primary.cmd 为空 | 在输出中将"推荐下一步"替换为 `{primary.reason}` 单行（Rule 4 已完成场景） |

## 与其他 skill 的边界

| skill | 职责 | 与 next 的关系 |
|-------|------|----------------|
| `mint:status` | 状态快照（quality / 产物 / blocker 详情） | next 尾部附表只提进度，详情让用户跳 status |
| `mint:init` | 工作区初始化 | next 遇未初始化报错并指向 init |
| 9 个流水线 skill 末尾引导块 | 每个 skill 执行完自动调一次 compute_next_hints 输出引导 | next 是用户主动触发的全景版 |
