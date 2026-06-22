---
name: rpiv-loop:handoff
description: 长程任务跨会话打结 + 续会话冷启动。**本 skill 仅负责创建新 handoff 或 mark-consumed 已有 handoff**，把当前会话的状态、决策、待办、教训持久化成 handoff 文件，下次会话首条消息引用即可机械化恢复。当用户提到"打个结"、"生成 handoff"、"创建 handoff"、"今天到这"、"明天接着"、"暂停一下"、"切别的话题"、"/rpiv-loop:handoff" 时触发。**用户意图为"查看 / 列出 / 看一下 pending handoff" 时, 禁止触发本 skill, 改用 `/rpiv-loop:handoff-list` 命令 (fast path, 不加载 SOP)**。也适用于：完成显著 milestone 后用户切换任务、context window 用量明显增长、跨日推进同一长程任务。**配套双层 hook 自动检测**：(1) SessionStart hook 启动时扫 cwd + 直接子目录的 pending handoff，命中即注入 system context；(2) UserPromptSubmit hook 在会话**首条 user prompt** 时再次注入 prompt 前缀强提醒 (用 ~/.claude/handoff_first_prompt_seen.json 跟踪 session_id, 同会话只注入一次)。两层叠加保证: 即使 LLM 漏看 SessionStart 注入, 也会在第一条用户消息时被 UserPromptSubmit 强制提醒, 你必须先用 AskUserQuestion 询问用户是否推进 handoff 再处理用户原始请求。注意：本 skill 的 "handoff" 是 Claude Code 社区"跨会话打结"语义（非 OpenAI Agents SDK 的多 agent 间运行时转移）。状态机仅 pending → archived 两状态，handoff 是一次性票据，被新会话消费后即归档。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 2.1.14
---

# Handoff: 跨会话长程任务交接

## 用法

```bash
# 创建新 handoff（默认模式）
/rpiv-loop:handoff

# 显式新生文件（即使距上次 < 2h）
/rpiv-loop:handoff --new-file

# 标记已消费（由 bootstrap prompt 自动调用，不需要手动跑）
/rpiv-loop:handoff --mark-consumed rpiv/handoff-YYYY-MM-DD-v<n>.md

# 列出当前项目所有 pending handoff (fast path, 不走本 skill)
/rpiv-loop:handoff-list           # 列 pending
/rpiv-loop:handoff-list --all     # 连 archived 一起列
```

## 核心概念（动手前必读）

### 状态机（仅 2 状态）

```
[/rpiv-loop:handoff create]
   ↓
pending  ──────────  存在，待下次会话消费
   │
   │  新会话首条消息: 引用本 handoff 路径作为 bootstrap
   │  bootstrap prompt 顶部含: /rpiv-loop:handoff --mark-consumed <path>
   ↓  (status: pending → archived + 写 consumed_at)
archived ──────────  已消费，一次性票据
```

**handoff 是一次性票据**：每份 handoff 只服务一次会话续接，被消费后即归档。任务自然完成时 = `rpiv/` 里全是 archived 且无 pending = 任务已结。

### 与 compaction / memory 的区分

| 维度 | Compaction | **Handoff** | Memory |
|------|-----------|-------------|--------|
| 触发 | 自动、context 阈值 | **人为、会话末** | 显式 put，跨会话查询 |
| 范围 | 单会话内有损摘要 | **单任务跨会话续接** | 跨任务长期事实 |
| 载体 | 内存/prompt | **磁盘文件** | DB/Store/NeuroMem |

handoff 不替代 memory（长期事实存 file memory / NeuroMem）和 compaction（会话内 Claude Code 自动）。三者并存。

### 与 OpenAI Agents SDK 名词区分

OpenAI Agents SDK 的 "handoff" 是**多 agent 间运行时控制权转移**。本 skill 的 "handoff" 是 **Claude Code 社区"跨会话打结"语义**。同名异义，不要混淆。

## 模式 A: create（默认）

### 流程

1. **定位项目 handoff 目录**
   - cwd 下有 `rpiv/` → 用 `rpiv/`
   - 否则降级到 `handoff/`（不存在则 mkdir）
2. **扫已有 handoff，确定 v\<n\>**
   - `Glob "**/handoff-*.md"` 找全部
   - 解析文件名末尾 `v<N>`，取 max+1（首次 = v1）
3. **判断 edit vs new-file**
   - 找最新 handoff（按 mtime + frontmatter `created_at`）
   - `created_at` 距今 < 2h **且** 用户没传 `--new-file` → 默认 edit 模式（追加到已有 section 后）
   - 否则 → 新生文件
4. **互动收集 4 段必填内容**（用 AskUserQuestion）
   - 段 1：bootstrap prompt 填充字段（project_path / progress_files / memory_key / next_steps[1-3]）
   - 段 2：TL;DR（本会话产出 ✅/⛔/⏸️ bullet）
   - 段 3：下一步动作 + 推荐方向
   - frontmatter description 由 TL;DR 第一条自动派生
5. **询问是否填 reference template 选段**（最多一次 AskUserQuestion，多选）
   - 默认全部 skip，用户多选才填
6. **完整性门禁校验**
   - 4 段必填段中任一为空、仅含占位符（`TODO` / `N/A` / `<...>` / `xxx`）→ 报错退出
7. **写文件 + 输出 bootstrap prompt**

### Edit 模式合并策略

- TL;DR：在末尾追加新一组 bullet（保留旧 bullet）
- 时间线段（如存在）：追加新行
- 状态快照段（如存在）：追加新段落，旧段落不删
- 下一步动作段：**覆盖**（旧的下一步已过时）
- bootstrap prompt block：**覆盖**（路径不变但 next_steps 更新）
- 同时更新 `updated_at`

### Create 模式必填段 schema

```yaml
---
description: "[handoff] <TL;DR 第一条派生的一句话>"
status: pending
created_at: <ISO>
updated_at: <ISO>
archived_at: null
consumed_at: null
---
```

**段 1：⭐ 下次会话第一步（复制粘贴）**

```markdown
## ⭐ 下次会话第一步（复制粘贴）

\```
cd <PROJECT_PATH>
读 <HANDOFF_RELATIVE_PATH> (本 handoff, 最新)
读 <PROGRESS_FILES>  # 任务级 source of truth
读 ~/.claude/projects/<MEMORY_KEY>/memory/MEMORY.md  # 项目级 file memory (如有)

调用 /rpiv-loop:handoff --mark-consumed <HANDOFF_RELATIVE_PATH>

按本 handoff "下一步动作" 段:
1. <NEXT_STEP_1>
2. <NEXT_STEP_2>
3. <NEXT_STEP_3>
\```
```

**段 2：TL;DR**

```markdown
## TL;DR

- ✅ <本会话主要产出 1>
- ✅ <本会话主要产出 2>
- ⛔ <阻塞或问题, 如有>
- ⏸️ <暂停的事项, 下次接>
```

**段 3：下一步动作**

```markdown
## 下一步动作（新会话主动执行）

1. <第一步具体动作, 含调用的 skill / 读的文件>
2. <第二步>
3. <第三步>

### 推荐方向（如有多选）

| 方向 | 描述 | 推荐度 |
|------|------|--------|
| A | <方向 A 描述> | ⭐⭐⭐ |
| B | <方向 B 描述> | ⭐⭐ |
```

### 完整性门禁检查清单

skill 在写文件**之前**检查以下条件，任一失败立即报错退出（不写部分文件）：

| 检查项 | 失败示例 |
|--------|---------|
| frontmatter 4 字段完整 | 缺 `status` / `created_at` 等 |
| ⭐ 段含 `cd ` + `读 ` + `/rpiv-loop:handoff --mark-consumed` | 用户略过填写 |
| TL;DR 至少 1 条 bullet | 空段 |
| 下一步动作至少 1 条 | 空段 |
| 无占位符残留 | `TODO` / `N/A` / `<NEXT_STEP_1>` 等未填充 |

报错信息模板：
```
⛔ handoff 必填段缺失或残留占位符:
  - 段: <段名>
  - 问题: <具体问题>
  请补全后重试。skill 已退出, 未写文件。
```

## 模式 B: --mark-consumed

由新会话冷启动时按 bootstrap prompt 自动调用。

### 流程

1. 读取目标 handoff frontmatter
2. 按 status 分支：

| 当前 status | 动作 |
|------------|------|
| `pending` | 改为 `archived` + 写 `consumed_at: <now>` + `updated_at: <now>` → 输出 `✅ 已消费 <path>` |
| `archived` | warn `⚠️ 已于 <consumed_at> 消费过`，AskUserQuestion 询问"是否重新激活"。yes → 改回 pending + 清 `consumed_at`；no → 不变 |
| 其他（罕见，如手动改） | 报错 `⛔ status=<x> 不在预期范围 (pending/archived)，请人工检查 frontmatter` |

3. mark-consumed **不读 handoff 正文**，只动 frontmatter，避免污染消费会话上下文（正文由消费会话自己 Read 触发）。

## 模式 C: --list-pending

```bash
/rpiv-loop:handoff --list-pending
```

扫 cwd 下 `rpiv/handoff-*.md`（无 rpiv/ 则 `handoff/`），列出所有 `status: pending` 的文件，按 mtime 倒序。

输出：
```
Pending handoff (N):
- rpiv/handoff-2026-05-22-v14.md (created 2026-05-22 22:10, updated 2026-05-22 22:30)
- rpiv/handoff-2026-05-15-v8.md (created 2026-05-15 09:00, updated 2026-05-15 09:00) [⚠️ 距今 7 天未消费]
```

`N > 1` 时输出 warn："⚠️ 多份 pending handoff 同时存在，工作流可能出错。预期应为 0 或 1。"

## 模式 D: SessionStart hook 自动检测（v1.1.0 起）

新会话启动时（matcher `startup|clear|resume`）自动跑 `hooks/handoff_detector.py`，检测 pending handoff 并在 system context 中注入提醒。**无需手动调用**，作为 mode C 的"被动触发"对照面。

### 行为

1. **扫描范围**：cwd + cwd 的直接子目录（深度 ≤2），匹配 `<dir>/rpiv/handoff-*.md` 和 `<dir>/handoff/handoff-*.md`
2. **黑名单排除**：`.git` / `node_modules` / `.venv` / `__pycache__` / `dist` / `build` / `.next` / `target` / 隐藏目录（`.` 开头）
3. **过滤**：仅 frontmatter `status: pending` 才计入
4. **排序**：优先 frontmatter `updated_at`，fallback `mtime`，最新在前
5. **stale 标红**：距今 ≥7 天加 `[⚠️ 距今 N 天未消费]` 视觉提示
6. **静默返回**：cwd 下 + 直接子目录均无 pending → exit 0 不注入任何东西
7. **错误兜底**：脚本任何异常静默 exit 0，绝不阻塞会话启动

### 注入文本格式

```
🎯 检测到 N 份 pending handoff (cwd: <path>):

📍 **当前项目 (./)** - K 条:
  [1] `rpiv/handoff-2026-05-27-v1.md`  [今天更新]
      📝 <description>
      → /rpiv-loop:handoff --mark-consumed rpiv/handoff-2026-05-27-v1.md

📂 **子项目 sub_a/** - M 条:
  · `sub_a/rpiv/handoff-2026-05-15-v0.md`  [⚠️ 距今 12 天未消费]
      📝 <description>
      → /rpiv-loop:handoff --mark-consumed sub_a/rpiv/handoff-2026-05-15-v0.md

---
**请在本次会话开头主动用 AskUserQuestion 询问用户:**
- 是否要 mark-consumed 某份 handoff 并按其 bootstrap prompt 推进
- 还是先做别的 (跳过本次提醒)
```

### Claude 收到此 context 应做的事

注入文本末尾明确要求：**首条回复中主动用 AskUserQuestion 询问用户是否继续推进**。选项至少含：
1. "推进 [1] - <最新 pending 的 description>" → 读该 handoff + 调 `/rpiv-loop:handoff --mark-consumed <path>` + 按 bootstrap prompt 推进
2. "推进 [其他编号]"（多份时）
3. "跳过本次提醒，先做别的"（用户当前有别的任务，本次会话不消费 pending）
4. "归档某份"（stale 太久已无意义）

注意：单纯 Read handoff **不会**改 status，必须显式调 `--mark-consumed`。

### 与模式 C `--list-pending` 的关系

| 维度 | 模式 C `--list-pending` | 模式 D SessionStart hook |
|------|------------------------|--------------------------|
| 触发 | 用户主动调用 | 新会话启动自动 |
| 输出渠道 | terminal stdout | system context（Claude 可见）|
| 扫描深度 | cwd 一层 | cwd + 直接子目录（≤2）|
| 失败影响 | 报错 | 静默（不阻塞）|
| 适用场景 | 怀疑有遗忘的 pending | 防止"不知道有 handoff 待续" |

### Hook 部署位置

- 脚本：`D:/CODE/plugins/rpiv-loop/hooks/handoff_detector.py`
- 注册：`D:/CODE/plugins/rpiv-loop/hooks/hooks.json` 的 `SessionStart` 块（matcher `startup|clear|resume`）
- 调用：`uv run --no-project python "${CLAUDE_PLUGIN_ROOT}/hooks/handoff_detector.py"`

cc-dev 模式加载本 plugin 时自动注册；sync-claude 同步给其他设备后随 plugin 一起生效。

## Source-of-truth 文件分层（强烈建议）

handoff **不是** 进度追踪器。**任务进度事实**（如 import 了哪些文件、跑了哪些命令、issue 状态）应落到独立 append-only 文件：

| 文件类型 | 推荐路径 | 内容 |
|---------|---------|------|
| 进度日志 | `scripts/.import_log/progress.jsonl` | append-only，每条 ISO 时间戳 + 操作 + 结果 |
| 任务清单 | `rpiv/todo/<feature>.md` | 长期任务状态 |
| memory_id 速查 | handoff 内含或独立 `scripts/.ids.jsonl` | 跨会话查 ID |

create 时，AskUserQuestion 问用户"本任务有没有 source-of-truth 文件需要在 bootstrap prompt 里引用？"，用户可填多个路径（逗号分隔），自动写入段 1 的 `读 <PROGRESS_FILES>` 行。

**handoff 自身仅记录状态摘要 + 决策上下文**，不重抄进度。这是 14 份 know-me 实证后的最佳实践。

## 元规则 / 经验沉淀升级路径

某些跨会话强制约束（如 know-me 的"含人名前必须先 recall"）会在 handoff 间累积。当一条元规则**跨项目可复用**时，建议升级到更长期的载体：

| 范围 | 载体 |
|------|------|
| 本项目跨会话 | handoff 元规则段 |
| 跨项目跨会话 | `~/.claude/projects/<MEMORY_KEY>/memory/feedback_*.md` (file memory) |
| 跨设备跨项目 | NeuroMem（mcp__neuromem__ingest） |

create 时如用户填了"元规则"段，skill 在结尾提示："本会话沉淀了 N 条元规则，其中跨项目可复用的考虑写入 file memory / NeuroMem。"

## 完整 Reference Template（可选 8 段）

用户在 create 时按需选填。

### 选段 1：本会话操作时间线

```markdown
## 本会话操作时间线

| 时间 | 动作 | 备注 |
|------|------|------|
| HH:MM | <动作> | <备注> |
```

### 选段 2：当前状态快照

```markdown
## 当前 <系统名> 状态 (YYYY-MM-DD HH:MM)

| 维度 | 数量 / 状态 |
|------|-------------|
| <维度 1> | <值> |
```

### 选段 3：关键文件清单

```markdown
## 关键文件清单

| 文件 | 用途 |
|------|------|
| <path> | <用途> |
| <path> | **★ source of truth** |
```

### 选段 4：元规则

```markdown
## 元规则（新会话务必遵守）

- <规则 1>
- <规则 2>
```

### 选段 5：关键 ID 速查

```markdown
## 关键 ID 速查（本会话）

| ID | 内容 | 操作时间 |
|----|------|---------|
| `<id>` | <内容> | <时间> |
```

### 选段 6：经验沉淀

```markdown
## 经验沉淀（跨会话价值）

1. <经验 1>
2. <经验 2>
```

### 选段 7：开放追问清单

```markdown
## 开放追问清单

### A. <问题 A>
<状态 / 上下文>

### B. <问题 B>
<状态 / 上下文>
```

### 选段 8：教训锚点

```markdown
## 教训锚点

- <教训 1>
- <教训 2>
```

## 触发关键词（SKILL.md description 已声明）

主动触发：
- `/handoff` / `/rpiv-loop:handoff`
- "打个结" / "生成 handoff" / "做个交接"
- "今天到这" / "明天接着" / "下班了" / "暂停一下"
- "切别的话题" / "换个事做"

Claude 主动 propose 信号（仅询问不 auto-execute）：
- 完成显著 milestone（多个 todo 标 completed + 用户说 "完成 / OK / perfect"）
- 用户语义出现暂停 / 切换 / 休息意图
- context window 用量明显增长（如出现 compaction 提示）

## 错误处理

| 场景 | 处理 |
|------|------|
| cwd 无 rpiv/ 也无 handoff/ | 自动 mkdir handoff/ |
| 找不到任何 handoff (首次) | v1 + 不写 supersedes 字段 |
| 必填段空或占位符 | 报错退出，未写文件 |
| --mark-consumed 路径不存在 | 报错 `⛔ 文件不存在: <path>` |
| --mark-consumed status 异常 | warn + AskUserQuestion 询问 |
| 同会话 2h 内重复 create | 默认 edit，提示 "检测到同会话 (上次 <时间>)，将 update 本份" |

## 注意事项

1. **handoff 是一次性票据**：被消费后归档，不要尝试反复用同一份 handoff 续多个会话
2. **不写 supersede 链**：frontmatter 不含 `supersedes` / `superseded_by` 字段，演化追溯靠文件名时间序
3. **mark-consumed 必须显式调用**：单纯 Read handoff 不会改状态，必须按 bootstrap prompt 调 `--mark-consumed`
4. **跨设备 / 重读**：archived → pending 重激活罕见，需用户确认。多份 pending 同时存在 = 工作流出错
5. **任务自然完成**：无独立 close 动作，最后一份停 archived 即可。整条链可后续用 `/rpiv-loop:archive` 批量归档（虽然已是 archived，archive skill 会跳过 status=archived 文件，无副作用）
6. **不要把 handoff 当 task tracker**：进度事实落 progress.jsonl / todo，handoff 只存状态摘要 + 决策上下文
