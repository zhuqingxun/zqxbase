---
name: mint:summarize
description: >-
  MINT 跨会议汇总——interview 工作区生成 V2.0 风格跨会议报告 (纯观点 / 观点+原声 / 深度洞察).
  支持按 interviewee_type 拆分主产物, 支持用户提供观点汇总样例模板, 默认增量模式保留人工编辑, `--full` 触发全量重建.
  当用户说"汇总全部访谈""生成综合洞察""summarize""跨会议汇总"时触发.
  仅 interview 场景可用, 要求工作区已完成 types/templates 登记且至少一个会议 polish=completed.
argument-hint: "[--full] [--split | --no-split]"
allowed-tools: Read, Write, Edit, Bash, Glob, Agent, AskUserQuestion
version: 2.1.11
---


# mint:summarize — 跨会议汇总

> **`{MINT_REF}` 路径约定**: 指 mint 插件的 `references/` 目录, `{MINT_SCRIPTS}` 为同级 `scripts/` 目录. 首次引用时通过
> `Glob("**/plugins/mint/references/next-hints-template.md")` 定位, 多结果时优先非 `marketplaces/` 路径 (私有开发版).

> **v3.0 变更**: prompt 输出格式重设为 V2.0 实证风格 (无受访者编号 / 综合论证骨架 / 子主题分类). 新增**按 interviewee_type 拆分主产物**配置 (`split_by_type`) + **观点汇总样例模板**配置 (`viewpoint_template_path`). 产物 1+2 受配置控制, 产物 3 (深度洞察) 永远 1 份.

把 interview 工作区下 N 份已完成 polish 的会议产物汇总为 V2.0 风格跨会议报告, 消除手工编辑负担的同时, 保留用户多轮人工润色.

## 用法

```
/mint:summarize [--full] [--split | --no-split]
```

- 无参: 默认增量模式. 若无快照或首次运行自动降级为全量.
- `--full`: 强制全量重建 (等价于 v1 行为).
- `--split` / `--no-split`: 临时覆盖 `summarize.split_by_type` 配置, 不写回 workspace.yaml.

## 前置条件

1. 当前工作目录是 interview 工作区根 (即含 `.mint/workspace.yaml` 且 `workspace.scenario == "interview"`)
2. `workspace.yaml.interviewee_types[]` 和 `workspace.yaml.templates[]` 均非空
3. 至少一个会议 `stages.polish.status == "completed"` 且 `meta.yaml.interviewee_type` 已填
4. 不合规时 skill 透传 summarize-collect CLI 的报错消息

## 产出物

3 份 Markdown 报告写入 `<工作区>/汇总分析/`. **产物 1+2 数量受 `split_by_type` 配置控制**, 产物 3 永远 1 份:

### 拆模式 (`split_by_type=true`)

| 文件 | 内容 | 数量 |
|------|------|------|
| `mint_纯观点汇总_<type 名>.md` | V2.0 综合论证, 无原声, 无受访者编号 | × N (N=interviewee_types 数) |
| `mint_观点原声汇总_<type 名>.md` | V2.0 综合论证 + 每观点末原声段 | × N |
| `mint_深度洞察.md` | 跨会议模式识别 + 根因分析 + Start/Stop/Continue 建议 | × 1 (永不拆) |

### 合模式 (`split_by_type=false`)

| 文件 | 内容 | 数量 |
|------|------|------|
| `mint_纯观点汇总.md` | V2.0 综合论证, 顶级 `## 一、<type 名>视角` 章节区分 type | × 1 |
| `mint_观点原声汇总.md` | V2.0 综合论证 + 原声段, 同上 type 二级章节区分 | × 1 |
| `mint_深度洞察.md` | 同上 | × 1 |

### 增量辅助产物

| 文件 | 用途 |
|------|------|
| `汇总分析/.summarize-state.json` | 快照: 所有会议 polish 源 sha256 + workspace 当前 types/templates 顺序 + outputs 动态列表 + split_mode + template_used 标识 |
| `汇总分析/.summarize-diff-<ts>.md` | 本次变更说明 (added/changed/removed + append 详单 + stale 详单) |

**文件名 `mint_` 前缀**: 与用户手工产物共存不冲突; 重跑时仅 `mint_*.md` 会被迁移到 `old/{timestamp}/`.

---

## 执行流程

### 第 0 步: 配置加载 + AskUserQuestion 触发

读取 `<root>/.mint/workspace.yaml` 的 `summarize:` 块:

```yaml
summarize:
  split_by_type: true|false       # 仅控产物 1+2, 产物 3 永远 1 份
  viewpoint_template_path: <path>  # 观点汇总样例路径 (相对工作区根, 可空)
```

#### 0.1 split_by_type 决策

按以下顺序确定本次运行的 `split_mode`:

1. CLI flag `--split` / `--no-split` 优先 (临时覆盖, 不写 workspace.yaml)
2. workspace.yaml `summarize.split_by_type` 字段已存在 → 直接用
3. 工作区只有 1 个 interviewee_type → 强制 `split_mode = true` (无意义可拆), 不问, 不写字段
4. ≥2 type 且字段不存在 → 走 0.3 步问

#### 0.2 viewpoint_template_path 决策

按以下顺序确定本次运行的格式参考样例:

1. workspace.yaml `summarize.viewpoint_template_path` 字段已存在 → 读取该文件全文 (前 N 行节选, 限制 ≤ 200 行) 作为 `{{viewpoint_format_reference}}` 占位符注入内容
2. 字段不存在 → 走 0.3 步问

如果用户跳过模板提供, 则注入**内置 V2.0 默认样例**: Read `{MINT_REF}/summarize-default-viewpoint-format-v2.md` (本指引附带的内置样例, 见本目录下伴随文件; 若该文件不存在, 用 prompt 内嵌的简短默认描述)

#### 0.3 AskUserQuestion (一次性问)

仅当 0.1 或 0.2 需要询问时触发, 一次问 1-2 个问题:

**问题 1 (仅 0.1 需问时)**: `检测到工作区有 ≥2 个 interviewee_type, 是否按 type 拆分主产物 (纯观点 + 观点原声) 为多个文件? 深度洞察始终 1 份不变.`

选项:
- `合并 (推荐)`: 单文件按 type 二级章节区分, `split_by_type=false`
- `拆分`: 每个 type 一个文件, `split_by_type=true`

**问题 2 (仅 0.2 需问时)**: `是否提供观点汇总样例文件以适配本项目格式? 不提供则用内置 V2.0 默认风格作为默认.`

选项:
- `使用内置默认 V2.0 风格 (推荐)`: 不写字段
- `提供 .md 样例路径`: AskUserQuestion 二次询问路径 (用户输入字符串路径), 验证文件存在 + 是 .md 后写入 workspace.yaml `summarize.viewpoint_template_path` 字段
- `跳过本次, 后续可在 workspace.yaml 加`: 不写字段, 本次用内置默认

写回 workspace.yaml 用 Edit 工具, 保留其他字段不变.

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
3. 否则调 `summarize-detect-delta` (传入第 0 步决策的 split_mode):
   ```bash
   DELTA_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-detect-delta "<工作目录>" --split-mode <true|false>)
   ```
   - `delta.first_run == true` (含旧 schema state.json 自动降级) → 走**全量路径**并标注"旧 schema 自动升级"
   - `delta.workspace_reorder == true` → 报错退出: `ERROR: workspace types/templates 顺序已变化, 增量模式不支持重排, 请用 /mint:summarize --full`
   - `delta.split_mode_changed == true` (state 中 split_mode 与本次 split_mode 不同) → 报错退出: `ERROR: split_by_type 配置已变化 (旧: <X>, 新: <Y>), 增量模式不支持模式切换, 请用 /mint:summarize --full`
   - 其他 → 走**增量路径** (第 0-X 步)

---

## ===== 增量路径 =====

### 第 0 步: 无变更短路 (Delta 空判)

若 `delta.added + delta.changed + delta.removed + delta.new_types + delta.new_templates` **全部为空**:

1. 构造新 state: 复用 `detect-delta` 返回的 `current_meetings / current_types_order / current_templates_order`, `outputs` 字段从旧 state 原样继承; `ts` 刷新为当前 ISO 时间戳
2. 调 `summarize-write-state` 落盘
3. stdout 输出简短无变更报告并退出, 不做 backup, 不生成 `.summarize-diff-<ts>.md`, 不修改主文件:

```
mint:summarize 完成.

模式: incremental (无变更)
覆盖会议: <N_eligible> 个 (internal <Ni> / external <Ne> / leader <Nl>)
本次变更: added=0 changed=0 removed=0
快照文件: 汇总分析/.summarize-state.json (ts 已刷新)

产出物未变动; 如需重建请 /mint:summarize --full.

<末尾引导块 from next-hints-template.md>
```

### 第 I 步: Delta 分析与锚点定位

1. 解析 delta JSON. 关键字段: `added[]` / `changed[]` / `removed[]` / `new_types[]` / `new_templates[]` / `current_meetings{}` / `current_types_order[]` / `current_templates_order[]`
2. 根据 `split_mode` 计算需要 append 的目标文件清单:
   - **拆模式**: 对每个受影响 type, 目标文件为 `mint_纯观点汇总_<type>.md` 和 `mint_观点原声汇总_<type>.md` (产物 1+2)
   - **合模式**: 目标文件为 `mint_纯观点汇总.md` 和 `mint_观点原声汇总.md` (产物 1+2, 单文件)
   - 产物 3 (`mint_深度洞察.md`) 仅插入 stale 注释, 不 append
3. 对每个目标文件调 `summarize-find-anchors`:
   ```bash
   ANCHORS=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-find-anchors "<file>")
   ```
   返回 `headings[]`, 每个 heading 含 `level / text / line_start / line_end / content_end / parent_line`.
4. 构造 append 计划:
   - **拆模式锚点**: 直接锚 `### 【问题 N: ...】` (level=3) 的 `content_end + 1`
   - **合模式锚点**: 锚 `## 一、<type 名>视角` (level=2) 内的 `### 【问题 N: ...】` (level=3); 用 `parent_line` 过滤到对应 type 章节内的问题章节

**parent_line 过滤** (仅合模式): 同名 `### 【问题 1: ...】` 在 internal / external 下都会出现; 必须用 `parent_line` (对应的 `## 一、<type>视角` heading 行号) 过滤到当前受访者所属 type 下的问题章节.

### 第 II 步: 受删除会议的 AskUserQuestion 确认

若 `delta.removed` 非空:

1. 对每个 removed meeting, 在当前观点原声主文件 (拆模式: 所有 N 份; 合模式: 单份) 中 grep 该会议 polish 源中的关键短语 (从 polish 源前 200 字提取一短语作 fingerprint), 记录受影响段落 line 范围
2. 调 **AskUserQuestion** (multiSelect=true):
   - question: `检测到以下 N 个会议已从工作区移除, 勾选需要删除其观点段落的会议 (未勾选默认保留, 标 stale):`
   - options: `[{label: "<dir> (定位 L<start>-L<end>, <N> 行)", description: "删除段落"}, ...]`
3. 用户勾选 → 计入"removed 段落清单" (后续第 VII 步执行删除)

**注**: V2.0 风格无受访者编号, 段落定位需依赖 polish 源关键短语指纹 + meeting_dir → 主张句的回溯, 比 v2 字母编号定位略复杂, 不唯一时降级为"标 stale 不删除".

### 第 III 步: Token 预算检查 (增量专属)

只对 `delta.added + delta.changed` 的 polish 源总量做 180KB 检查 (沿用 v2):

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

调 `summarize-backup-outputs`:

```bash
BACKUP_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-backup-outputs "<工作目录>")
```

`{ts}` 用 `%Y-%m-%dT%H-%M-%S`. 备份范围由 `summarize-backup-outputs` CLI 根据 state.json `outputs[]` 列表动态确定 (拆模式备份 2N+1 份, 合模式备份 3 份).

备份完成后, 主文件已被**移走**. 增量路径需从备份目录拷贝回作为 append 基底:

```bash
for f in <state.json outputs[*].path>; do
  cp <root>/汇总分析/old/<ts>/$(basename $f) <root>/汇总分析/$f
done
```

### 第 V 步: 生成 append 片段 (产物 1+2 共享)

对 `delta.added ∪ delta.changed` 每个受访者并行启动 Agent:

1. Read `polish_source_abs` 得到受访者 polish 源全文
2. Read `{MINT_REF}/summarize-append-interviewee-prompt.md`
3. 启动 Agent (subagent_type="general-purpose"), prompt 含:
   - Part 1 元数据 (meeting_dir / 受访者代号 / interviewee_type / 是否脱敏稿)
   - Part 2 该 type 的提纲问题清单 (从基底主文件中按章节顺序抽出)
   - Part 3 polish 源全文
   - 末尾附 `{MINT_REF}/summarize-append-interviewee-prompt.md` 全文作为 System Prompt
4. Agent 返回 JSON → 解析:
   - 验证 `fragments[*].question_num` 在 Part 2 问题编号集合内 (非法项跳过)
   - 验证每条 fragment 的 `markdown_only` 和 `markdown_quote` 均以 `<EDITION>` 起始
   - 验证 `markdown_only` 不含 `原声:` (产物 1 无原声), `markdown_quote` 含 `原声:`
5. 若整体 JSON 解析失败 → 记录该受访者"append 失败", 继续下一受访者, 最终 diff 报告列出失败项

**并发策略**: 多个受访者的 Agent 在同一消息中并行启动.

**changed 会议处理**: 若 changed 会议原已有段落 → 先删除原段落 (用 polish 源 fingerprint 定位), 再 append 新段落. 无法精确定位时跳过删除, 在 diff 报告标注"changed 段落可能重复, 请手工合并".

### 第 VI 步: 执行 append (倒序 splice + `<EDITION>` 替换)

对每个 fragment, 分别 append 到产物 1 (`markdown_only`) 和产物 2 (`markdown_quote`) 对应文件:

1. 计算插入位置: `target_line = anchor.content_end + 1` (按 `split_mode` 选锚点)
2. **替换 `<EDITION>` 占位符为具体编号**:
   - Read 该问题章节的最后一条观点行, 检测编号风格:
     - 数字风格 (`1. **xxx**` / `2. **xxx**`) → `<EDITION>` → `<最大数字+1>.`
     - 观点 N 风格 (`**观点 1:**` / `**观点 2:**`) → `<EDITION>` → `**观点 <最大数字+1>:**`
     - 章节为空 (无既有观点) → 默认数字风格, `<EDITION>` → `1.`
   - 用 Python str.replace 在 fragment markdown 中替换占位符
3. fragment markdown 前后加换行做段落分隔: `content = "\n" + fragment.markdown + "\n"`
4. 调 `summarize-splice-text`:
   ```bash
   printf '%s' "$content" | uv run --script {MINT_SCRIPTS}/meta_io.py summarize-splice-text "<root>/汇总分析/<目标文件>" --at-line <target_line> --mode before
   ```
5. 记录 inserted_at 行号到 diff 报告

**关键**: 按 `anchor.content_end` 从**大到小**排序处理所有 fragment, 避免每次插入后重算锚点. 同一 fragment 跨产物 1+2 的 splice 互不影响 (不同文件).

**新 type / 新 template** (拆模式): 若 delta.new_types 非空, 需先创建新文件 `mint_纯观点汇总_<新 type>.md` 和 `mint_观点原声汇总_<新 type>.md`, 写入头部元数据 + 该 type 提纲问题骨架 (空 heading), 再 append 各受访者片段.

**新 type / 新 template** (合模式): 在主文件末尾 splice 新一级章节 `## N、<新 type>视角`, 内嵌该 type 的所有二级问题 heading, 再 append 各受访者片段.

### 第 VII 步: 执行 removed 段落删除

若第 II 步用户勾选了要删除的会议段落:

1. Read 当前主文件并定位段落 (用 polish 源关键短语指纹 + 段落边界匹配)
2. 用 Edit 工具:
   - `old_string`: 完整段落文本 (含前导空行)
   - `new_string`: ""
3. 校验 `old_string` 唯一: 不唯一时 → 记入 diff 报告"段落定位歧义, 标 stale 不删除", 跳过

### 第 VIII 步: 插入 / 合并 stale 注释 (产物 1+2 + 产物 3)

对每个受影响章节:

1. 产物 1 (纯观点): 受影响章节 = (受影响 type, 受影响问题); 拆模式锚 `### 【问题 N: ...】`; 合模式锚 `## 一、<type>视角` 内的 `### 【问题 N: ...】`
2. 产物 2 (观点原声): 同上, 但因第 V 步已 append, 通常不需要 stale (除非 changed 段落定位失败保留旧段)
3. 产物 3 (深度洞察): 全部 `added ∪ changed ∪ removed` 触发整段 stale (锚 `## 核心发现` heading)

stale 合并逻辑沿用 v2 (`parse_stale` / `merge_stale` / `format_stale` 三函数, 在 meta_io.py 中).

### 第 IX 步: 更新 state.json (动态 outputs)

构造新 state:
```json
{
  "schema_version": 2,
  "ts": "<本次 run ISO timestamp>",
  "split_mode": <true | false>,
  "template_used": "<内置默认 | 用户路径>",
  "workspace_snapshot": {
    "types_order": <current_types_order>,
    "templates_order": <current_templates_order>
  },
  "meetings": <current_meetings>,
  "outputs": [
    {"role": "viewpoint_only", "type": "<type 名 | 空字符串(合模式)>", "path": "汇总分析/mint_纯观点汇总_<type>.md", "sha256": "<...>", "size_bytes": <...>, "mtime": "<...>"},
    {"role": "viewpoint_quote", "type": "<type 名 | 空字符串(合模式)>", "path": "汇总分析/mint_观点原声汇总_<type>.md", "sha256": "<...>", "size_bytes": <...>, "mtime": "<...>"},
    {"role": "insight", "type": "", "path": "汇总分析/mint_深度洞察.md", "sha256": "<...>", "size_bytes": <...>, "mtime": "<...>"}
  ]
}
```

`schema_version: 2` 表示 v3 起的新 schema (动态 outputs 列表). 旧 schema_version=1 (v2 硬编码 3 文件名) 在 detect-delta 时会触发 split_mode_changed 降级到全量.

`outputs[*].sha256/size_bytes/mtime` 通过 `summarize-sha256 <file>` 计算, 然后写入:

```bash
echo "$NEW_STATE_JSON" | uv run --script {MINT_SCRIPTS}/meta_io.py summarize-write-state "<工作目录>"
```

### 第 X 步: 生成 .summarize-diff-<ts>.md + stdout 摘要

Leader 用 Write 工具直接落盘 `<root>/汇总分析/.summarize-diff-<ts>.md`, 模板沿用 v2 + 末尾追加新固定区:

```markdown
# mint:summarize 变更报告

- 运行时间: <ISO_timestamp>
- 模式: incremental
- split_by_type: <true | false>
- 模板: <内置默认 | 用户路径 path>
- 触发变更: added=<N> changed=<N> removed=<N>
- Workspace 新增: new_types=<csv or 无> new_templates=<csv or 无>
- 备份目录: 汇总分析/old/<ts>/
- 快照文件: 汇总分析/.summarize-state.json

## 新增/变更/删除会议

| meeting_dir | type | 状态 | 产物 1 append | 产物 2 append | 产物 3 stale |
|---|---|---|---|---|---|
| <dir> | <type> | added | <M> 个 fragment | <M> 个 fragment | ✓ |
...

## 产物 1+2: append 详单

- `<file>:L<line>` ### 【问题 <N>: ...】 末尾 append <承接式主张句, 截前 30 字...> (<L> 行)
...

## 删除段落

- `<file>` 删除段落 (定位关键短语: <短语片段>) (L<start>-L<end>, <L> 行)

## 产物 3: stale 标记

- `mint_深度洞察.md:L<line>` ## 核心发现 stale 注释合并 new_meetings=<csv> changed_meetings=<csv> removed_meetings=<csv>

## 需手工介入的 changed 会议段落

(列出本次 changed 的会议及其影响章节, 供用户人工核对脱敏一致性)
- <dir>: 影响章节 X / Y / Z, 旧段落定位状态: <成功删除 | 跳过删除 (歧义)>
...

## 后续建议

- 如需重写产物 1+2 以融合新会议为主张, 运行 `/mint:summarize --full`
- 如果任何 fragment 质量不满意, 可手工 Edit 对应段落; 下次增量不会重写
```

stdout 摘要 (跳到"两路径汇合"最后一步).

---

## ===== 全量路径 =====

### 第 A 步: Backup + 提纲问题提取 + 模板节选

**A.1 Backup**:

```bash
BACKUP_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py summarize-backup-outputs "<工作目录>")
```

**A.2 提纲问题提取** (沿用 v2):

对 `templates[]` 每个 template, 按文件后缀分派:

- `.md` 提纲: 直接 Read, 全文作为 `template_text`
- `.pdf` 提纲: 调 `pdf_extract.py "<template.file_abs>"`; 失败 → `parse_status: failed`
- 为每个 template 启动 Agent 抽问题清单 (subagent_type="general-purpose", prompt 含 `{MINT_REF}/summarize-template-questions-prompt.md`). 多 template 并行启动.
- 若**所有** template 失败 → 整体进入"无提纲模式"

**A.3 模板节选准备 (新增, 给产物 1+2 的 prompt 注入用)**:

根据第 0 步决策的 `viewpoint_template_path`:

- 字段空 (使用内置默认): Read `{MINT_REF}/summarize-default-viewpoint-format-v2.md` (本插件附带), 全文作为 `viewpoint_format_reference`
- 字段有值: Read `<root>/<viewpoint_template_path>`, 取前 200 行 (或全文若 < 200 行) 作为 `viewpoint_format_reference`
- 都失败 → 用兜底字符串 `(未提供格式参考样例; 请按本指引正文规则输出)`

**A.4 Token 预算检查 + 构造输入**:

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

按拆/合模式构造 `llm_input_material`:

- **拆模式**: 为每个 type 单独构造一份 input 材料 (Part 3 仅含该 type 受访者), 共 N 份输入 → 后续 Agent 调用按 type 分别跑
- **合模式**: 1 份 input 材料 (Part 3 按 type 分组列出全部受访者) → 1 次 Agent 调用产出 1 份合并文件

各 input 材料的 Part 1 元数据中标明 `split_mode` 和 `当前 type` (拆模式) / 空字符串 (合模式).

### 第 B 步: Agent 调用 (按拆/合模式分支)

#### B 拆模式: 2N + 1 次 Agent 调用 (按 type 串行 + 立即 Write)

对每个 type, 串行跑产物 1 + 产物 2 (`split_mode=true` 输入材料):

- B.split.1.<type>: Agent (System=`{MINT_REF}/summarize-viewpoint-only-prompt.md`, Part 4 注入 `viewpoint_format_reference`) + 该 type input → Write `mint_纯观点汇总_<type>.md`
- B.split.2.<type>: Agent (System=`{MINT_REF}/summarize-viewpoint-quote-prompt.md`, Part 4 注入 `viewpoint_format_reference`) + 该 type input → Write `mint_观点原声汇总_<type>.md`

最后跑产物 3 (1 次):

- B.split.3: Agent (System=`{MINT_REF}/summarize-insight-prompt.md`) + 全 type input → Write `mint_深度洞察.md`

#### B 合模式: 3 次 Agent 调用 (串行 + 立即 Write)

- B.combine.1: Agent (System=`{MINT_REF}/summarize-viewpoint-only-prompt.md`, Part 4 注入 `viewpoint_format_reference`) + 合模式 input → Write `mint_纯观点汇总.md`
- B.combine.2: Agent (System=`{MINT_REF}/summarize-viewpoint-quote-prompt.md`, Part 4 注入 `viewpoint_format_reference`) + 同 input → Write `mint_观点原声汇总.md`
- B.combine.3: Agent (System=`{MINT_REF}/summarize-insight-prompt.md`) + 同 input → Write `mint_深度洞察.md`

#### Agent 失败处理

每步 Agent 返回后立即 Write 落盘. Agent 失败 → 当前产物写空壳含错误说明, 跳下一步; 后续 stdout 报告列"失败产物清单".

### 第 C 步: 写入 state.json (动态 outputs)

调用 `summarize-sha256` 计算所有产出文件的 sha256/size/mtime, 构造 state JSON (结构与增量第 IX 步一致, schema_version=2, outputs 字段含本次实际产出的所有文件), 调 `summarize-write-state` 写入.

---

## ===== 两路径汇合 =====

### 最后一步: 末尾引导块 + stdout 报告

**末尾引导块** (沿用 v2):

```bash
HINTS_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py workspace-recommendation "<工作目录>")
```

若 CLI 失败 → 固定默认 `primary=/mint:next --all`, reason="查看工作区全景下一步".

**渲染引导块**: Read `{MINT_REF}/next-hints-template.md` → 填充 `{primary_cmd}` / `{primary_reason}` / `{alternatives_block}`.

**stdout 最终输出**:

```
mint:summarize 完成.

模式: incremental / full (标注首次生成 (无快照) / workspace_reorder 降级 等)
拆分模式: split_by_type=<true | false> (拆 N 份 / 合 1 份)
模板: <内置默认 V2.0 | 用户路径 path>
覆盖会议: <N_eligible> 个 (internal <Ni> / external <Ne> / leader <Nl>)
本次变更 (增量模式): added=<N> changed=<N> removed=<N> (全量模式写 "全量重建")
跳过会议: <N_skipped> 个 <skipped 清单或 "无">
使用提纲: <template_names_csv> (或 "无提纲模式")

产出物 (动态列表, 拆模式 N+1 份 / 合模式 3 份):
- <root>/汇总分析/mint_纯观点汇总_<type 名>.md (<size>KB)  [拆模式 × N]
- <root>/汇总分析/mint_纯观点汇总.md (<size>KB)  [合模式]
- <root>/汇总分析/mint_观点原声汇总_<type 名>.md (<size>KB)  [拆模式 × N]
- <root>/汇总分析/mint_观点原声汇总.md (<size>KB)  [合模式]
- <root>/汇总分析/mint_深度洞察.md (<size>KB)  [永远 1 份]

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
| summarize-detect-delta 返回 split_mode_changed=true | 报错退出, 建议 `/mint:summarize --full` |
| summarize-read-state 抛 ValueError (state.json 损坏 / schema_version 旧) | 透传错误消息, 建议用户手工删除 `.summarize-state.json` 后改用 `/mint:summarize --full` |
| 提纲 PDF 解析返回空或 pdf_extract.py exit 非 0 | 标记该 template `parse_status: failed`; 若全部 template 失败 → 整体进入无提纲模式 |
| 用户提供的 viewpoint_template_path 文件不存在或非 .md | 警告但不阻塞, 降级为内置默认; 在 stdout 末尾标注"模板文件不可读, 已用内置默认" |
| Agent 返回 fragments JSON 校验失败 | 记录该受访者 append 失败, 继续处理其他受访者; 最终 diff 报告列出 |
| Agent 调用失败 (网络 / 超时 / 返回空) | 保留已完成的产物, 当前产物写入空壳 (含错误说明), 跳到下一步 |
| summarize-splice-text 返回非 0 | 透传错误退出 |
| stale 合并失败 (parse_stale 异常) | 降级到 new stale 覆盖 (忽略旧 state) |
| Token 预算超限 (增量 delta > 180KB 或全量 > 180KB) | 报错退出并建议拆分 / 改 --full / 等 |
| summarize-backup-outputs 备份目录已存在 | 透传 FileExistsError 错误消息退出; 用户等 1 秒重跑 |
| `汇总分析/` 目录不存在 | skill 自动 mkdir; Write 工具也会自动创建父目录 |
| 合格会议但 polish_source_abs 文件读取失败 | collect CLI 已保证文件存在; 若仍失败 → 报错退出 |
| workspace-recommendation CLI 失败 | 降级到 compute-next-hints; 若仍失败, 末尾引导块用固定默认 |
| `<EDITION>` 占位符替换失败 (检测既有编号风格异常) | 默认数字风格 1, 在 diff 报告标注"编号检测降级" |

---

## 质量控制

### Leader 自检 (每份产物生成后)

| 维度 | 检查要点 |
|------|---------|
| 头部元数据完整 | 覆盖清单 / 跳过清单 / 使用提纲 / ISO 时间戳均填充 (全量模式) |
| 章节结构符合 V2.0 骨架 | `### 【问题 N: ...】` 三级标题 + 全角【】+ 前置 blockquote `> - **核心问题:** ...` |
| 无受访者编号 | grep `受访者_\d+` / `受访者 [A-Z]` / `\d{2}_\w+` 应为 0 处 |
| 无原声引号引用 (产物 1) | 产物 1 (纯观点) 中 `"..."` 长句应为 0 处 |
| 有原声段 (产物 2) | 产物 2 中每观点末有 `   原声:` 标签 + 列表 |
| 无会议编号 inline 引用 (产物 3) | 产物 3 中 `01_xxx` 等会议编号应为 0 处 |
| 无真实姓名泄漏 | 不从原稿反推真实姓名 |
| 增量模式未变章节字节级保留 | 对比 backup 的同章节文本, 未变章节应字节级完全一致 |

Leader 自检不做深度语义核查; 只做格式层快速检查, 失败不阻塞但记入 stdout 报告.

---

## 只读守护 (关键约束)

summarize 是**只读消费 + 有限写产物**:

- **只读**: `workspace.yaml` (除 summarize 配置块外) / `meta.yaml` / `desensitization_registry.yaml` / polish 产物
- **只写**:
  - `<root>/汇总分析/mint_*.md` (动态文件名, 拆/合模式)
  - `<root>/汇总分析/old/{ts}/*.md`
  - `<root>/.mint/workspace.yaml` (仅 summarize 配置块: `split_by_type` / `viewpoint_template_path`, 写回需用 Edit 保留其他字段)
- **增量新增白名单**: `<root>/汇总分析/.summarize-state.json` + `<root>/汇总分析/.summarize-diff-*.md` 可读可写
- **严禁**: 修改任何 meta.yaml / desensitization_registry.yaml / workspace.yaml 中 summarize 块以外的字段; 删除任何用户手工产物 (非 `mint_` 前缀文件); 触碰 polish 阶段产物

违反只读约束会被回归测试的 SHA-256 bytewise 对比检出.
