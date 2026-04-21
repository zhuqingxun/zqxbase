---
name: mint:summarize
description: >-
  MINT 跨会议汇总——interview 工作区生成三份跨会议报告 (观点+原声 / 纯观点 / 深度洞察).
  默认增量模式保留人工编辑, `--full` 触发全量重建.
  当用户说"汇总全部访谈""生成综合洞察""summarize""跨会议汇总"时触发.
  仅 interview 场景可用, 要求工作区已完成 types/templates 登记且至少一个会议 polish=completed.
allowed-tools: Read, Write, Edit, Bash, Glob, Agent, AskUserQuestion
version: 2.1.5
---


# mint:summarize — 跨会议汇总

> **`{MINT_REF}` 路径约定**: 指 mint 插件的 `references/` 目录, `{MINT_SCRIPTS}` 为同级 `scripts/` 目录. 首次引用时通过
> `Glob("**/plugins/mint/references/next-hints-template.md")` 定位, 多结果时优先非 `marketplaces/` 路径 (私有开发版).

> **v2.0 变更**: 新增**增量模式**. 默认走增量 (只为新增/变更会议生成片段, 保留人工编辑), `--full` 回退到 v1 全量重建. 首次运行或快照缺失自动降级到全量.

把 interview 工作区下 N 份已完成 polish 的会议产物汇总为 3 份跨会议报告 (观点+原声 / 纯观点 / 深度洞察), 消除手工编辑负担的同时, 保留用户多轮人工润色.

## 用法

```
/mint:summarize [--full]
```

- 无参: 默认增量模式. 若无快照或首次运行自动降级为全量.
- `--full`: 强制全量重建 (等价于 v1 行为).

## 前置条件

1. 当前工作目录是 interview 工作区根 (即含 `.mint/workspace.yaml` 且 `workspace.scenario == "interview"`)
2. `workspace.yaml.interviewee_types[]` 和 `workspace.yaml.templates[]` 均非空
3. 至少一个会议 `stages.polish.status == "completed"` 且 `meta.yaml.interviewee_type` 已填
4. 不合规时 skill 透传 summarize-collect CLI 的报错消息

## 产出物

3 份 Markdown 报告写入 `<工作区>/汇总分析/`:

| 文件 | 内容 | 预估大小 |
|------|------|---------|
| `mint_观点原声汇总.md` | 按 type 分一级章节 + 按提纲问题分二级章节 + 每人观点 + 原声引用 | 10-15 KB |
| `mint_纯观点汇总.md` | 同结构去原声 + 同一问题下多人观点融合为群像段落 | 8-12 KB |
| `mint_深度洞察.md` | 跨会议模式识别 + 根因分析 + Start/Stop/Continue 建议 | 6-10 KB |

增量模式下新增两份辅助产物:

| 文件 | 用途 |
|------|------|
| `汇总分析/.summarize-state.json` | 快照: 所有会议 polish 源 sha256 + workspace 当前 types/templates 顺序 |
| `汇总分析/.summarize-diff-<ts>.md` | 本次变更说明 (added/changed/removed + append 详单 + stale 详单) |

**文件名 `mint_` 前缀**: 与用户手工产物 (`访谈观点汇总.docx` 等) 共存不冲突; 重跑时仅 `mint_*.md` 会被迁移到 `old/{timestamp}/`.

---

## 执行流程

### 第一步: 数据采集 (两路径共享)

调 `summarize-collect` CLI 一次拿齐决策数据 (scenario + types/templates + 合格会议清单 + polish 源路径 + 新增 sha256/size/mtime).

```bash
COLLECT_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-collect "<工作目录>")
```

失败 (exit 非 0, stderr 含 `ERROR:`) → 直接透传错误消息并退出. 常见错误:
- `ERROR: summarize 仅 interview 场景可用`
- `ERROR: 请先 /mint:templates add 注册访谈提纲`
- `ERROR: 无合格 polish 产物, 请先跑 /mint:polish`

解析 JSON 得:
- `scenario`, `types[]`, `templates[]` (含 `file_abs`)
- `eligible_meetings[]` (含 `dir / project / interviewee_type / polish_source_abs / is_desensitized / polish_sha256 / polish_size_bytes / polish_mtime`)
- `skipped_meetings[]` (含 `dir / reason`)

### 第二步: 模式决策

1. 若 `$ARGUMENTS` 含 `--full` token → 跳到 **全量路径** (第 A-C 步)
2. 否则调 `summarize-read-state`:
   ```bash
   STATE_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-read-state "<工作目录>")
   ```
   若返回 `null` (首次运行) → 走**全量路径**并在最终 stdout 标注"首次生成 (无快照)"
3. 否则调 `summarize-detect-delta`:
   ```bash
   DELTA_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-detect-delta "<工作目录>")
   ```
   - `delta.workspace_reorder == true` → 报错退出: `ERROR: workspace types/templates 顺序已变化, 增量模式不支持重排, 请用 /mint:summarize --full`
   - 其他 → 走**增量路径** (第 0-X 步)

---

## ===== 增量路径 =====

### 第 0 步: 无变更短路 (Delta 空判)

若 `delta.added + delta.changed + delta.removed + delta.new_types + delta.new_templates` **全部为空**:

1. 构造新 state: 复用 `detect-delta` 返回的 `current_meetings / current_types_order / current_templates_order`, `outputs` 字段从旧 state 原样继承 (三份主文件未变动, 无需重算 sha256); `ts` 刷新为当前 ISO 时间戳
2. 调 `summarize-write-state` 落盘
3. stdout 输出简短无变更报告并退出, 不做 backup, 不生成 `.summarize-diff-<ts>.md`, 不修改三份主文件:

```
mint:summarize 完成.

模式: incremental (无变更)
覆盖会议: <N_eligible> 个 (internal <Ni> / external <Ne> / leader <Nl>)
本次变更: added=0 changed=0 removed=0
快照文件: 汇总分析/.summarize-state.json (ts 已刷新)

产出物未变动; 如需重建请 /mint:summarize --full.

<末尾引导块 from next-hints-template.md>
```

**Why**: 无 delta 时执行 backup + stale 插入 + diff 报告都属于多余动作, 会污染 `old/` 目录, 在深度洞察中插入空 stale 注释, 并生成垃圾 diff 报告.

### 第 I 步: Delta 分析与锚点定位

1. 解析 delta JSON. 关键字段: `added[]` / `changed[]` / `removed[]` / `new_types[]` / `new_templates[]` / `current_meetings{}` / `current_types_order[]` / `current_templates_order[]`
2. 对三份主文件 (`mint_观点原声汇总.md` / `mint_纯观点汇总.md` / `mint_深度洞察.md`) 分别调 `summarize-find-anchors`:
   ```bash
   ANCHORS_QUOTE=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-find-anchors "<root>/汇总分析/mint_观点原声汇总.md")
   ANCHORS_VIEW=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-find-anchors "<root>/汇总分析/mint_纯观点汇总.md")
   ANCHORS_INSIGHT=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-find-anchors "<root>/汇总分析/mint_深度洞察.md")
   ```
   返回每份文件的 `headings[]`, 每个 heading 含 `level / text / line_start / line_end / content_end / parent_line`.
3. 构造执行计划:
   - **观点原声 append 计划**: 每个 `added ∪ changed` 会议 × 其 type 提纲问题数 = M 个 fragment 位置; 锚点为 `### 【问题 N: ...】` (level=3) 的 `content_end + 1`
   - **纯观点 stale 计划**: 每个受影响二级/三级章节 → 1 个 stale 注释 (插入到 heading 下一行 before)
   - **深度洞察 stale 计划**: `## 核心发现` 整段视为受影响 → 1 个 stale 注释 (`added ∪ changed ∪ removed` 任一非空时触发; 全空时本步已在第 0 步短路退出, 不会进入本步)

**parent_line 过滤**: 观点原声中同名 `### 【问题 1: ...】` 在 internal / external 下都会出现; 必须用 `parent_line` (对应的 `## 一、内部员工视角` heading 行号) 过滤到当前受访者所属 type 下的问题章节.

### 第 II 步: 受删除会议的 AskUserQuestion 确认

若 `delta.removed` 非空:

1. 对每个 removed meeting, 在当前 `mint_观点原声汇总.md` 中 grep `**受访者 X**（<meeting_dir>` 字样, 记录其段落 line 范围 (从 `**受访者 X**（` 行到下一个 `**受访者 ` 行或父章节边界)
2. 调 **AskUserQuestion** (multiSelect=true):
   - question: `检测到以下 N 个会议已从工作区移除, 勾选需要删除其观点原声段落的会议 (未勾选默认保留):`
   - options: `[{label: "<dir> (L<start>-L<end>, <N> 行)", description: "删除段落"}, ...]`
3. 用户勾选 → 计入"removed 段落清单" (后续第 VII 步执行删除)

### 第 III 步: Token 预算检查 (增量专属)

只对 `delta.added + delta.changed` 的 polish 源总量做 180KB 检查:

```bash
total_bytes=0
for src in <delta.added ∪ delta.changed 的 polish_source_abs>; do
  size=$(wc -c < "$src")
  total_bytes=$((total_bytes + size))
done
if [ "$total_bytes" -gt 184320 ]; then
  echo "ERROR: delta polish 产物总量 ${total_bytes} bytes 超 180KB, 建议拆分 delta 或改用 --full" >&2
  exit 1
fi
```

### 第 IV 步: Backup

调 `summarize-backup-outputs` (与 v1 一致; 即使增量也全量备份三份主文件到 `old/{ts}/`):

```bash
BACKUP_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-backup-outputs "<工作目录>")
```

`{ts}` 用 `%Y-%m-%dT%H-%M-%S` (Windows 禁冒号); 此 ts 将复用于本次 diff 报告文件名.

**注意**: 备份完成后, `汇总分析/mint_*.md` 已被**移走**. 对于增量路径, 需要从备份目录 `old/<ts>/` 拷贝回三份主文件到 `汇总分析/` 下作为 append 基底:

```bash
cp <root>/汇总分析/old/<ts>/mint_*.md <root>/汇总分析/
```

### 第 V 步: 生成 append 片段 (仅观点原声)

对 `delta.added ∪ delta.changed` 每个受访者并行启动 Agent:

1. Read `polish_source_abs` 得到受访者 polish 源全文
2. Read `{MINT_REF}/summarize-append-interviewee-prompt.md`
3. 计算"该 type 下已出现的最后一个受访者字母" (从基底 `mint_观点原声汇总.md` 中 grep `**受访者 \w**（<同 type 会议的 meeting_dir>`)
4. 启动 Agent (subagent_type="general-purpose"), prompt 含:
   - Part 1 元数据 (meeting_dir / 受访者代号 / interviewee_type / 是否脱敏稿 / 该 type 下一字母)
   - Part 2 该 type 的提纲问题清单 (从基底主文件中按章节顺序抽出, 或从第三步构造的材料中复用)
   - Part 3 polish 源全文
   - 末尾附 `{MINT_REF}/summarize-append-interviewee-prompt.md` 全文作为 System Prompt
5. Agent 返回 JSON → 解析:
   - 校验 `interviewee_label` 是否与 Leader 预期字母一致 (不一致: 降级强制采用 Leader 字母并覆写每个 fragment markdown 开头的 `**受访者 X**`)
   - 校验 `fragments[*].question_num` 是否在 Part 2 问题编号集合内 (非法项跳过)
6. 若整体 JSON 解析失败 → 记录该受访者"append 失败", 继续下一受访者, 最终 diff 报告列出失败项

**并发策略**: 多个受访者的 Agent 在同一消息中并行启动 (Claude Code 支持同消息内多个 Agent 调用并发).

**changed 会议处理**: 若 changed 会议原已有段落 → 先删除原段落 (用 Edit, old_string=段落完整文本 + 前导空行, new_string=""), 再用新 label append. 若无法精确定位原段落 → 跳过删除, 只 append 新段落并在 diff 报告标注"changed 会议段落可能重复, 请手工合并".

### 第 VI 步: 执行观点原声 append (倒序 splice)

**关键**: 按 `anchor.content_end` 从**大到小**排序处理所有 fragment, 避免每次插入后重算锚点.

对排序后每个 fragment:

1. 计算插入位置: `target_line = anchor.content_end + 1`
2. fragment markdown 前后加换行做段落分隔: `content = "\n" + fragment.markdown + "\n"`
3. 调 `summarize-splice-text`:
   ```bash
   printf '%s' "$content" | uv run --script {MINT_SCRIPTS}/meta_io.py summarize-splice-text "<root>/汇总分析/mint_观点原声汇总.md" --at-line <target_line> --mode before
   ```
4. 记录 inserted_at 行号到 diff 报告

**新 type / 新 template**: 若 delta.new_types 非空, 在当前文件没有对应 `## N、<type_name>视角` 一级章节, 需先 Write 或 splice 新一级章节骨架到文件末尾 (heading + 本 type 的所有二级问题 heading), 再按上述流程 append 各受访者片段.

### 第 VII 步: 执行 removed 段落删除

若第 II 步用户勾选了要删除的会议段落:

1. Read 当前 `mint_观点原声汇总.md` 并定位 `**受访者 X**（<meeting_dir>` 所在段落 (起始行 → 下一个 `**受访者 ` 开头或父级章节结束)
2. 用 Edit 工具:
   - `old_string`: 完整段落文本 (含前导空行)
   - `new_string`: ""
3. 校验 `old_string` 唯一: 受访者段落因含 `meeting_dir` 通常全文唯一; 不唯一时 → 记入 diff 报告"段落定位歧义, 手工删除", 跳过

### 第 VIII 步: 插入 / 合并 stale 注释 (纯观点 + 深度洞察)

对每个受影响章节:

1. Read 目标 heading 的下一行内容 (即 `line_start + 1` 行)
2. 计算本章节 delta-local:
   - 纯观点: 根据章节所属的 (type, 问题编号) 筛选 `added ∪ changed ∪ removed` 中哪些 meeting 的 interviewee_type 对应本 type 且该 meeting 在本问题有回答 (若无法精确判断哪些问题, 可保守地将该 type 所有受影响 meeting 都列为本章节的 delta-local)
   - 深度洞察: 全部 `added ∪ changed ∪ removed` (跨会议洞察)
3. 用 Bash 内联 Python 调 `parse_stale` 解析下一行:
   ```bash
   python -c "
   import sys
   sys.path.insert(0, '{MINT_SCRIPTS}')
   from meta_io import parse_stale, merge_stale, format_stale
   import json
   old_line = <heading 下一行原文 base64 或 stdin>
   delta_local = {'new': <...>, 'changed': <...>, 'removed': <...>}
   ts = <本次 run ts>
   old_state = parse_stale(old_line)
   merged = merge_stale(old_state, delta_local, ts)
   print(format_stale(merged))
   "
   ```
4. 若下一行已有 stale → 用 Edit 替换整行 (old_string=原行, new_string=新 stale 注释)
5. 否则 → 调 `summarize-splice-text --at-line <heading.line_start+1> --mode before` (stdin=stale 注释 + 换行)

### 第 IX 步: 更新 state.json

构造新 state:
```json
{
  "schema_version": 1,
  "ts": "<本次 run ISO timestamp>",
  "workspace_snapshot": {
    "types_order": <current_types_order>,
    "templates_order": <current_templates_order>
  },
  "meetings": <current_meetings>,
  "outputs": {
    "mint_观点原声汇总.md": {"sha256": <...>, "size_bytes": <...>, "mtime": <...>},
    "mint_纯观点汇总.md": {"sha256": <...>, "size_bytes": <...>, "mtime": <...>},
    "mint_深度洞察.md": {"sha256": <...>, "size_bytes": <...>, "mtime": <...>}
  }
}
```

`outputs.*.sha256/size_bytes/mtime` 分别调 `summarize-sha256 <file>` 获取, 然后调:

```bash
echo "$NEW_STATE_JSON" | uv run --script {MINT_SCRIPTS}/meta_io.py summarize-write-state "<工作目录>"
```

### 第 X 步: 生成 .summarize-diff-<ts>.md + stdout 摘要

Leader 用 Write 工具直接落盘 `<root>/汇总分析/.summarize-diff-<ts>.md`, 模板:

```markdown
# mint:summarize 变更报告

- 运行时间: <ISO_timestamp>
- 模式: incremental
- 触发变更: added=<N> changed=<N> removed=<N>
- Workspace 新增: new_types=<csv or 无> new_templates=<csv or 无>
- 备份目录: 汇总分析/old/<ts>/
- 快照文件: 汇总分析/.summarize-state.json

## 新增/变更/删除会议

| meeting_dir | type | 状态 | 观点原声 append | 纯观点 stale | 深度洞察 stale |
|---|---|---|---|---|---|
| <dir> | <type> | added | <M> 个 fragment | N 章节 | ✓ |
...

## 观点原声汇总: append 详单

- `mint_观点原声汇总.md:L<line>` ### 【问题 <N>: ...】 末尾 append `**受访者 X**（<dir>...）` 段落 (<L> 行)
...

## 删除段落

- `mint_观点原声汇总.md` 删除 `**受访者 X**（<dir>...）` 段落 (L<start>-L<end>, <L> 行)

## 纯观点 / 深度洞察: stale 标记

- `mint_纯观点汇总.md:L<line>` ### 【问题 N: ...】 stale 注释合并 new_meetings=<csv> changed_meetings=<csv> removed_meetings=<csv>
...

## 后续建议

- 如需重写纯观点/深度洞察以融合新会议, 运行 `/mint:summarize --full`
- 如果任何 fragment 质量不满意, 可手工 Edit 对应段落; 下次增量不会重写
```

stdout 摘要 (跳到"两路径汇合"最后一步).

---

## ===== 全量路径 =====

### 第 A 步: Backup + 提纲问题提取 + 构造输入

**A.1 Backup** (沿用 v1 第七步-a):

```bash
BACKUP_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-backup-outputs "<工作目录>")
```

**A.2 提纲问题提取** (沿用 v1 第二步):

对 `templates[]` 每个 template, 按文件后缀分派:

- **`.md` 提纲**: 直接 Read, 全文作为 `template_text`
- **`.pdf` 提纲**: 调 `uv run --script {MINT_SCRIPTS}/pdf_extract.py "<template.file_abs>"`; 若 stdout 长度 < 100 字符或 exit 非 0 → 标记 `parse_status: failed`; 否则 stdout 作为 `template_text`
- 为每个 template 启动 Agent 抽问题清单 (subagent_type="general-purpose", prompt 含 `{MINT_REF}/summarize-template-questions-prompt.md`). 多 template 并行启动.
- 若**所有** template 失败 → 整体进入"无提纲模式"

**A.3 Token 预算检查 + 构造输入** (沿用 v1 第三步):

```bash
total_bytes=0
for src in <eligible_meetings[*].polish_source_abs>; do
  size=$(wc -c < "$src")
  total_bytes=$((total_bytes + size))
done
if [ "$total_bytes" -gt 184320 ]; then
  echo "ERROR: polish 产物总量 ${total_bytes} bytes 超 180KB, 请拆分工作区" >&2
  exit 1
fi
```

按 v1 第三步的三段式 (Part 1 元数据 / Part 2 提纲 / Part 3 按 type 分组受访者稿件) 构造 `llm_input_material`.

### 第 B 步: 三份 Agent 调用 (串行 + 立即 Write)

沿用 v1 第四/五/六步:

- 第 B.1 步: Agent (System=`{MINT_REF}/summarize-viewpoint-quote-prompt.md`) + `llm_input_material` → Write `mint_观点原声汇总.md`
- 第 B.2 步: Agent (System=`{MINT_REF}/summarize-viewpoint-only-prompt.md`) + 同 material → Write `mint_纯观点汇总.md`
- 第 B.3 步: Agent (System=`{MINT_REF}/summarize-insight-prompt.md`) + 同 material → Write `mint_深度洞察.md`

**串行执行**: 每步 Agent 返回后立即 Write 落盘, 避免失败丢失. Agent 失败 → 当前产物写空壳含错误说明, 跳下一步.

### 第 C 步: 写入 state.json (为下次增量准备)

调用 `summarize-sha256` 分别计算三份主文件的 sha256/size/mtime, 构造 state JSON (结构与增量第 IX 步一致, meetings 字段用本次 collect 得到的 current_meetings), 调 `summarize-write-state` 写入.

---

## ===== 两路径汇合 =====

### 最后一步: 末尾引导块 + stdout 报告

**末尾引导块** (沿用 v1 第八步 compute-next-hints 逻辑):

summarize 不修改 meta.yaml / workspace.yaml, 故跳过 `refresh-last-action`. 直接调:

```bash
HINTS_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py workspace-recommendation "<工作目录>")
```

若 CLI 失败 → 固定默认 `primary=/mint:next --all`, reason="查看工作区全景下一步".

**渲染引导块**: Read `{MINT_REF}/next-hints-template.md` → 填充 `{primary_cmd}` / `{primary_reason}` / `{alternatives_block}`.

**stdout 最终输出**:

```
mint:summarize 完成.

模式: incremental / full (标注首次生成 (无快照) / workspace_reorder 降级 等)
覆盖会议: <N_eligible> 个 (internal <Ni> / external <Ne> / leader <Nl>)
本次变更 (增量模式): added=<N> changed=<N> removed=<N> (全量模式写 "全量重建")
跳过会议: <N_skipped> 个 <skipped 清单或 "无">
使用提纲: <template_names_csv> (或 "无提纲模式")

产出物:
- <root>/汇总分析/mint_观点原声汇总.md (<size>KB)
- <root>/汇总分析/mint_纯观点汇总.md (<size>KB)
- <root>/汇总分析/mint_深度洞察.md (<size>KB)

增量辅助 (仅 incremental 模式):
- <root>/汇总分析/.summarize-state.json (快照, <size>B)
- <root>/汇总分析/.summarize-diff-<ts>.md (详单)

旧产物备份: <backup_dir 或 "无 (首次生成)">

<失败产物清单或 "全部产出物生成成功">

<末尾引导块 from next-hints-template.md>
```

---

## 异常处理

| 情况 | 处理 |
|------|------|
| summarize-collect CLI 失败 (非 interview / 无 templates / 无合格会议) | 透传 stderr 文本 + 退出 |
| summarize-detect-delta 返回 workspace_reorder=true | 报错退出, 建议 `/mint:summarize --full` |
| summarize-read-state 抛 ValueError (state.json 损坏) | 透传错误消息, 建议用户手工删除 `.summarize-state.json` 后改用 `/mint:summarize --full` |
| 提纲 PDF 解析返回空或 pdf_extract.py exit 非 0 | 标记该 template `parse_status: failed`; 若全部 template 失败 → 整体进入无提纲模式, 报告头部标注"无提纲模式" |
| Agent 返回 fragments JSON 校验失败 | 记录该受访者 append 失败, 继续处理其他受访者; 最终 diff 报告列出 |
| Agent 调用失败 (网络 / 超时 / 返回空) | 保留已完成的产物, 当前产物写入空壳 (含错误说明), 跳到下一步; 报告结果时列"失败产物清单" |
| summarize-splice-text 返回非 0 | 透传错误退出 |
| stale 合并失败 (parse_stale 异常) | 降级到 new stale 覆盖 (忽略旧 state) |
| Token 预算超限 (增量 delta > 180KB 或全量 > 180KB) | 报错退出并建议拆分 / 改 --full / 等 |
| summarize-backup-outputs 备份目录已存在 | 透传 FileExistsError 错误消息退出; 用户等 1 秒重跑即可 |
| `汇总分析/` 目录不存在 | skill 自动 mkdir; Write 工具也会自动创建父目录 |
| 合格会议但 polish_source_abs 文件读取失败 | collect CLI 已保证文件存在; 若本 skill Read 仍失败 → 报错退出, 提示用户检查文件权限 |
| workspace-recommendation CLI 失败 | 降级到 compute-next-hints; 若仍失败, 末尾引导块用固定默认 |

---

## 质量控制

### Leader 自检 (每份产物生成后)

| 维度 | 检查要点 |
|------|---------|
| 头部元数据完整 | 覆盖清单 / 跳过清单 / 使用提纲 / ISO 时间戳均填充 (全量模式) |
| 章节结构符合骨架 | 观点原声 / 纯观点: 按 type 分一级章节 + 按问题分二级/三级章节; 深度洞察: 核心发现 / 建议 / 方法论三段 |
| 受访者编号一致 | 同一会议全文用同一代号 (优先脱敏代号) |
| 无真实姓名泄漏 | 不从原稿反推真实姓名 (脱敏稿应保持代号) |
| 增量模式未变章节字节级保留 | 对比 backup 的同章节文本, 未变章节应字节级完全一致 (排除 append 新片段与 stale 注释) |

Leader 自检不做深度语义核查 (依赖人工验证清单); 只做格式层快速检查, 失败不阻塞但记入 stdout 报告.

---

## 只读守护 (关键约束)

summarize 是**只读消费 + 有限写产物**:

- **只读**: `workspace.yaml` / `meta.yaml` / `desensitization_registry.yaml` / polish 产物 (v1_polished_清洁稿.md 等)
- **只写**: `<root>/汇总分析/mint_*.md` + `<root>/汇总分析/old/{ts}/*.md`
- **增量新增白名单**: `<root>/汇总分析/.summarize-state.json` + `<root>/汇总分析/.summarize-diff-*.md` 可读可写
- **严禁**: 修改任何 meta.yaml / workspace.yaml / desensitization_registry.yaml 字段; 删除任何用户手工产物 (非 `mint_` 前缀文件); 触碰 polish 阶段产物

违反只读约束会被回归测试的 SHA-256 bytewise 对比检出, 任何 critical 失败会阻塞交付.
