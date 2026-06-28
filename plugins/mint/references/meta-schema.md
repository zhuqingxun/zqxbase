# meta.yaml Schema（会议级元数据）

本文件定义单个会议目录下 `meta.yaml` 的完整 schema。所有 mint session 级 skill 读写 meta.yaml 必须遵循本规范。

实际读写入口：`scripts/meta_io.py`（封装 yaml IO、规则推理、blocker 生命周期），SKILL.md 不直接 load/dump yaml。

## 字段顺序规范（强制）

save_meta 写入时必须保持以下顺序，禁止使用 `yaml.safe_dump` 的默认字母序输出：

```
project / created / source_audio / stages / revisions / desensitization / intent / interviewee_type / current / next_hints
```

## 完整 Schema

```yaml
# === 既有字段（保持不变）===

project: string                       # 会议名，必填
created: date                          # 会议创建日期（YYYY-MM-DD），必填
source_audio: string                   # 原始音频文件名，必填

stages:                                # 流水线四阶段状态，必填
  transcribe:
    status: enum[pending|in_progress|completed|failed]   # 必填
    version: int                                          # 可选
    completed_at: ISO8601                                 # completed 时必填
    params:                                               # 可选，stage 各自参数
      model: string
      speakers: int
  refine:
    status: enum[pending|in_progress|completed|failed]
    version: int
    completed_at: ISO8601
    params: object
    quality:                          # refine 专有质量评分（可选）
      fidelity: int                   # 0-10
      fluency: int
      consistency: int
      cleanliness: int
      format: int
  polish:
    status: enum[pending|in_progress|completed|failed]
    version: int
    completed_at: ISO8601
    desensitized: bool                # polish 是否做了脱敏
  extract:
    status: enum[pending|in_progress|completed|failed]
    version: int
    completed_at: ISO8601

revisions:                             # 修订历史列表，必填（初始 []）
  - timestamp: ISO8601
    type: string                       # 可选：修订来源，取值 patch | revise | sync（供 next-rules Rule 7/8 判断"最近动作类型"）
    description: string
    affected_files: list[string]       # 实际受影响文件的相对路径列表（非计数）；next-rules Rule 6a/6b 据此做 03_校对稿/* 等路径匹配

desensitization:                       # 脱敏映射（仅会议级局部映射），必填（初始 {name_map: {}}）
  name_map: object

# === 新增字段（本 PRD 引入，必填）===

intent:                                # 用户意图（首次使用时引导填写，后续沿用）
  goal: string                         # 本次会议的具体目标
  deliverables: list[string]           # 期望的交付物（如 [行动项, 要点摘要]）
  skip_stages: list[string]            # 明确要跳的阶段（如 [polish]）
  scenario: string                     # 可选 [interview|meeting]；为空时继承 workspace.scenario
                                       # 本 PRD 预留字段：规则引擎只存不读

interviewee_type: string | null        # 受访者类型 id，引用 workspace.interviewee_types[].id
                                       # interview 场景：新会议必填；polish 第零步会强校验
                                       # meeting 场景：恒为 null 或缺省
                                       # 历史遗留 polish.params.template / has_template 字段保留
                                       # 但 polish 新代码不再读取，新代码一律走 resolve-template

current:                               # 当前游标
  cursor: string                       # 最近活跃的阶段（"transcribe" / "refine" / "polish" / "extract"）
  last_action: ISO8601 | null          # 最近一次操作的时间（双源 max 计算，见下）
  last_action_desc: string             # 最近一次操作的描述
  blockers:                            # 待用户决策的阻塞项列表
    - type: enum[ambiguity|missing_input|user_decision]
      description: string
      suggested_action: string

next_hints:                            # 下一步候选（由各 skill 写入，由 next 命令和末尾引导块消费）
  primary:
    cmd: string                        # 推荐命令
    reason: string                     # 推荐理由（一句话）
  alternatives:
    - cmd: string                      # 备选命令
      when: string                     # 何时选它
```

## 字段语义与约束

### intent

- `goal` 会议级为空时，渲染输出应显示工作区级 goal（由 meta_io 读 workspace.yaml 兜底）
- `deliverables` 会议级为空时，同上继承工作区级预设
- `skip_stages` 影响 `compute_next_hints` 的 Rule 2 跳过逻辑
- `scenario` 只存不读，v1 规则引擎不消费此字段（将由后续 scenario PRD 接入）

### interviewee_type

- 取值范围为 `workspace.yaml` 中 `interviewee_types[].id` 列表 + `null`
- interview 场景下新建会议必填；由 polish 第零步 `resolve-template` 强校验
- meeting 场景恒为 `null`，polish 第零步直接视为"无模板模式"
- 不加入 `REQUIRED_META_FIELDS`（由 `load_meta` 校验）：缺字段校验下放到具体消费方（polish 第零步），避免破坏其他 skill
- 引用 workspace.yaml 的 type id 不存在时，polish 第零步报 `类型 <id> 不存在` 并 exit 2

### current.cursor

反映"最近活跃的阶段"，由各 session skill 在执行完成时更新。取值（**唯一真相**）：
- `transcribe` / `refine` / `polish` / `extract`（流水线阶段）或初始空串 `""`
- 维护类 skill（revise/patch/sync）**不改 cursor**（stays 语义）——只更新 `current.last_action_desc`，cursor 停留在最近的流水线阶段

> **契约对齐（2026-06-25，Part B 已迁移）**：`meta_io.set_cursor` 强制 cursor ∈ STAGE_ORDER（拒绝非阶段值）。`patch`/`revise`/`sync` 三个 SKILL.md 已改调 `meta_io.py add-revision --last-action-desc`，**不再写越界 cursor**——只更新 `current.last_action_desc`，cursor 停留在最近流水线阶段，代码层 / SKILL 层 / 本规范三方一致。历史 meta.yaml 中可能残留迁移前写入的越界 cursor 值（`"patch"` 等），消费方（status 渲染、scan_meetings）应继续容错。

### revisions

修订历史列表，每条记录一次维护操作。**唯一真相形态**（2026-06-24 对齐）：

```yaml
- timestamp: ISO8601          # 必填
  type: string                # 可选：patch | revise | sync
  description: string         # 必填：本次修订摘要
  affected_files: list[string] # 实际受影响文件相对路径（非计数）
```

- `affected_files` 记录**实际文件路径列表**，而非计数——这样 next-rules 的 Rule 6a/6b 才能据 `affected_files` 命中 `03_校对稿/*` / `04_编辑稿/*` 做下游推荐（见 [[fix-mint-next-rules-doc-code-drift]]）。
- 写入唯一入口：`meta_io.py add-revision`（`--desc` / `--files` / `--type` / `--last-action-desc`）。

> **契约对齐（2026-06-25，Part B 已迁移）**：`patch`/`revise`/`sync` 三个 SKILL.md 已改调 `add-revision` 写 `affected_files` 列表 + `type`，丢弃 `files_affected` 计数。`sync` 原 `source_file` 字段并入 `affected_files`（源文件即列表首项），不再单设——canonical 形态收敛为 `{timestamp, type, description, affected_files}` 四字段。历史 meta.yaml 中可能残留旧 `{files_affected, source_file}` 形态，消费方应容错。

### current.last_action 计算规则（双源 max）

```
last_action = max(
    max(stages.transcribe.completed_at, stages.refine.completed_at,
        stages.polish.completed_at, stages.extract.completed_at),
    max(revisions[*].timestamp)
)
```

伪代码（meta_io.refresh_last_action）：

```
def refresh_last_action(meta):
    candidates = []
    for stage_name, stage in meta["stages"].items():
        ts = stage.get("completed_at")
        if ts: candidates.append(ts)
    for rev in meta.get("revisions", []):
        ts = rev.get("timestamp")
        if ts: candidates.append(ts)
    if not candidates:
        meta["current"]["last_action"] = None
    else:
        # ISO 8601 字符串字典序 == 时间序（前提：格式固定 YYYY-MM-DDTHH:MM:SS）
        meta["current"]["last_action"] = max(candidates)
```

缺失场景：`candidates` 为空时写入 `null`，聚合排序时视为最低优先级。

### current.blockers 生命周期

```
            ┌──────────────────────────────────────────┐
            │                                          │
            │   refine/polish 检测到 ambiguity /        │
            │   missing_input / user_decision           │
            │                                          │
            └────────────────┬─────────────────────────┘
                             │ add_blocker(meta, b)
                             ▼
                    ┌─────────────────┐
                    │  blocker 持久化  │
                    │  in meta.yaml    │
                    └────┬───────┬────┘
                         │       │
      源头 skill 重跑评估  │       │  用户手动编辑
      predicate 返回 True │       │  meta.yaml 删除条目
                         ▼       ▼
              ┌─────────────────────────┐
              │    blocker 已解除         │
              │  （从 blockers[] 移除）   │
              └─────────────────────────┘
```

三种 type：
- `ambiguity`：文本歧义需用户澄清
- `missing_input`：缺少必要输入（如背景资料）
- `user_decision`：需要用户判断（如选用哪种脱敏强度）

自动解除触发条件：源头 skill（如 refine）再次执行时，传入 predicate 重新评估——若本次执行未再遇到同样问题，则从 blockers 列表移除。日志必须输出 `自动解除 blocker: <description>`（对应 PRD BLOCKER-01 断言）。

手动解除：用户可直接编辑 meta.yaml 的 blockers 数组删除条目，不引入专用命令（不做 mint:unblock）。

### next_hints

- `primary.cmd`：单个推荐命令字符串
- `primary.reason`：一句话原因
- `alternatives`：0 至 N 条备选，每条含 `cmd` 和 `when`
- 由各 session skill 调 `compute_next_hints` 写入，由 `mint:next` 和末尾引导块消费

## 缺字段报错行为

load_meta 执行时若缺少 `intent` / `current` / `next_hints` 三块中任何一块，必须抛出 KeyError，错误消息包含字段名（例如 `"meta.yaml 缺少必要字段 intent"`），对应 PRD NEG-02 / NEG-03 断言关键词。

v1 不做向后兼容：单用户单项目场景，现存工作区通过独立一次性升级脚本处理，skill 代码假定工作区已为新 schema。
