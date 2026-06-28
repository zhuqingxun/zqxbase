# .mint/workspace.yaml Schema（工作区级元数据）

本文件定义工作区级元数据文件 `.mint/workspace.yaml` 的完整 schema。工作区初始化唯一入口为 `mint:init`。

## 工作区根识别规则

- **工作区根** = 含 `.mint/workspace.yaml` 的目录
- **会议子目录** = 工作区根下含 `meta.yaml` 的一级子目录
- 不含 `meta.yaml` 的子目录（如 `汇总分析/`）一律忽略
- `.mint/` 本身在扫描 meetings 时必须被显式跳过

`find_workspace_root(cwd)` 行为：从 cwd 向上遍历 `cwd.parents`，返回首个含 `.mint/workspace.yaml` 的目录；到文件系统根仍未找到返回 `None`，上游 skill 据此输出"工作区未初始化，请先运行 /mint:init"。

## 完整 Schema

```yaml
workspace:
  name: string                         # 工作区名（默认 mint:init 时取 cwd basename）
  created_at: ISO8601                  # mint:init 写入时间
  scenario: enum[interview|meeting]    # 工作区级默认场景

intent:                                # 工作区级意图（mint:init 引导填写）
  goal: string                         # 项目目标（一句话）
  deliverables: list[string]           # 期望交付物预设（按 scenario 默认 + 用户 Q2 过滤）

# === 以下字段仅 interview 场景使用，meeting 场景可缺省 ===

interviewee_types:                     # 受访者类型注册表（强结构，会议必属其一）
  - id: string                         # kebab-case，正则 ^[a-z][a-z0-9-]*$
    name: string                       # 展示名（可含中文）
    default_template_id: string | null # 默认提纲 template id；可为 null（无默认）

templates:                             # 访谈提纲注册表（弱结构，可插拔）
  - id: string                         # kebab-case，通常带 tpl- 前缀
    name: string                       # 提纲展示名
    file: string                       # 相对工作区根的路径（建议 .mint/templates/<id>.ext）
    applies_to: list[string]           # 可用于哪些 interviewee_type id（至少 1 项）
```

## 字段顺序规范

save_workspace 写入时必须保持以下顺序：

```
workspace / intent / interviewee_types / templates
```

workspace 内部：`name / created_at / scenario`
intent 内部：`goal / deliverables`
interviewee_types 元素内部：`id / name / default_template_id`
templates 元素内部：`id / name / file / applies_to`

## 字段语义

### workspace.name

默认取 `mint:init` 执行时的 `cwd.name`（目录 basename）。允许用户在 workspace.yaml 中手动修改（本 PRD 不提供专用命令）。

### workspace.scenario

仅接受 `interview` 或 `meeting` 两值。`mint:init` 的 Q1 直接写入。v1 规则引擎不读此字段，预留供后续 scenario PRD 消费。

非法值处理（NEG-05）：读取时若 scenario 为预期枚举外的值，meta_io 宽容（不崩溃），但 mint:next / mint:init 的前置校验应输出警告或报错 `scenario 值非法`。

### intent.goal

用户在 `mint:init` Q3 填写的一句话项目目标，由 AskUserQuestion 的 4 预设选项 + 自动 Other 兜底获得。

### intent.deliverables

`mint:init` Q2 用户选中的多选项经 scenario 过滤后的最终列表。过滤规则详见 `scenario-presets.md`。

## 会议级继承规则

会议级 `meta.yaml.intent` 三字段（goal / deliverables / scenario）为空或缺失时，meta_io 读取时应从工作区级 workspace.yaml 继承：

- `meta.intent.goal == ""` → 用 `workspace.intent.goal`
- `meta.intent.deliverables == []` → 用 `workspace.intent.deliverables`
- `meta.intent.scenario == ""` → 用 `workspace.scenario`

继承仅在"读取合并视图"时应用，不写回 meta.yaml（保持 meta.yaml 级的空字段语义）。

## 持久化只此一处

`.mint/` 目录下允许两个持久化文件，外加一个可选 `templates/` 子目录：

```
<工作区根>/.mint/
├── workspace.yaml                 ← 见本 schema
├── desensitization_registry.yaml  ← 跨会议脱敏代号注册表（升级脚本迁入，格式不变）
└── templates/                     ← 可选：用户通过 mint:templates add 添加的提纲文件
    └── <tpl-id>.<ext>             ← 访谈提纲 PDF / Markdown 等，path 记录在 templates[].file
```

workspace-view（运行时聚合视图）不写盘，仅作文档术语。

`.mint/templates/` 子目录由 `mint:templates add` 按需创建（`Path.mkdir(parents=True, exist_ok=True)`），`scan_meetings` 已显式跳过 `.mint/` 不受影响。

## ID 约定与引用完整性

interviewee_types 与 templates 的 ID 规范、冲突处理、引用完整性规则详见 `types-templates.md`。
