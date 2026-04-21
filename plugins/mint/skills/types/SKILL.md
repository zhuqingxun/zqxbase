---
name: mint:types
description: >-
  MINT 受访者类型注册表管理——管理工作区级 interviewee_types[] 注册表。
  支持 add / list / remove 三子命令。
  当用户说"添加类型""登记受访者""types add""查看类型""删除类型""/mint:types"时触发。
  仅 interview 场景可用；polish 通过受访者类型选择对应提纲。
allowed-tools: Read, Bash, Glob, AskUserQuestion
version: 2.1.5
---

# mint:types — 受访者类型注册表管理

> **路径约定**：`{MINT_REF}` = mint 插件 `references/` 目录，`{MINT_SCRIPTS}` = 同级 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/mint/references/types-templates.md")` 定位，多结果时优先非 `marketplaces/` 路径。

管理工作区 `.mint/workspace.yaml` 中的 `interviewee_types[]` 注册表。每个会议的 `meta.interviewee_type` 必须引用本表中的某个 id。本 skill 是 `mint:init` 第 4 问的命令行等价物，供用户后续补充、查看或精简类型集。

## 用法

```
/mint:types add [<id>] [<name>] [--default-template <tpl-id>]
/mint:types list
/mint:types remove <id>
```

- 未指定 `<id>` / `<name>` 时通过 AskUserQuestion 交互补齐。
- 仅 interview 场景可用；meeting 场景调用会报错退出（由 meta_io 校验）。

## 执行流程

### 第一步：解析子命令

解析 `$ARGUMENTS` 的第一个 token 决定子命令分支：
- `add` → 跳到"第二步 A：add 流程"
- `list` → 跳到"第二步 B：list 流程"
- `remove` → 跳到"第二步 C：remove 流程"
- 空或其他 → 输出使用帮助并 exit 0

### 第二步：定位工作区根

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py find-workspace-root "$(pwd)"
```

- exit 0：stdout 为工作区根绝对路径，记为 `WS_ROOT`
- exit 1：输出 `错误：当前目录不在任何 mint 工作区内（未找到 .mint/workspace.yaml）。请先运行 /mint:init 初始化工作区。` 并 exit 1

### 第二步 A：add 流程

#### A.1 收集参数

从 `$ARGUMENTS` 剩余 token 解析位置参数 `<id>` 和 `<name>`，以及可选 `--default-template <tpl-id>`。

若缺参数，调用 **一次** AskUserQuestion 批次补齐（最多 3 问）：

- **Qa — name（单选 4 预设 + 自动 Other）**（仅 name 未提供时）
  - question: `新增受访者类型的展示名是什么?`
  - header: `类型名`
  - multiSelect: `false`
  - options（必须恰好 3 项，Claude Code 自动附加 Other）:
    - label: `内部员工` — description: `机构内部正式员工`
    - label: `外部员工 / 服务对象` — description: `业务服务对象/合作方员工`
    - label: `领导层` — description: `部门领导/高层管理者`

- **Qb — id（仅 id 未提供时）**
  - question: `自定义 id? (留空则由 name 自动生成 kebab-case)`
  - header: `类型 id`
  - multiSelect: `false`
  - options（2 项 + 自动 Other）:
    - label: `auto` — description: `由 name 自动生成（推荐，预设 name 命中映射表）`
    - label: `custom` — description: `手工指定一个 kebab-case id`

- **Qc — default template（仅存在 templates 注册表且用户未传 --default-template 时）**
  - question: `是否指定默认访谈提纲?`
  - header: `默认提纲`
  - multiSelect: `false`
  - options（动态生成 + `不设置` 选项，最多 4 项合计）:
    - label: `<tpl-id>` — description: `<tpl-name>`（取 templates[].id/name 前 3 项）
    - label: `不设置` — description: `暂不绑定默认提纲，可后续用 mint:templates add --set-default 回填`

#### A.2 规范化 id

若用户选 `auto` 或 Qb 未触发：
- id = PRESET_TYPE_ID_MAP.get(name)；不命中时走 `normalize_id(name, existing_ids)` 规则（详见 `{MINT_REF}/types-templates.md`）
- 直接使用 meta_io 内部的 `normalize_id` 逻辑，避免 skill 里重实现——通过 `types-add` CLI 的报错反馈处理非 ASCII 等情况。

#### A.3 调 CLI 写入

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py types-add "$WS_ROOT" "<id>" "<name>" [--default-template-id "<tpl-id>"]
```

成功：stdout 为 JSON `{"added": {...}}`，对用户渲染：
```
已添加类型：<id> (<name>)
默认提纲：<default_template_id | 未设置>
```

失败（exit 2）：透传 stderr `ERROR:` 消息并 exit 2。常见错误：
- `type id 已存在: <id>`
- `id 非法: <id>，必须匹配 ^[a-z][a-z0-9-]*$`
- `types 管理仅 interview 场景可用`
- `default_template_id <id> 未在 templates 注册表中`

### 第二步 B：list 流程

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py types-list "$WS_ROOT"
```

stdout 为 JSON 数组，每项含 `id / name / default_template_id / meetings_count / meetings`。

渲染表格：

```markdown
## 受访者类型注册表（{N} 项）

| id | name | 默认提纲 | 使用会议数 | 使用会议 |
|----|------|----------|------------|----------|
| internal | 内部员工 | tpl-internal | 3 | 01_A, 02_B, 03_C |
| external | 外部员工 / 服务对象 | tpl-external | 1 | 04_D |
```

空列表时输出：`当前工作区未注册任何 interviewee type，建议运行 /mint:types add 补齐。`

### 第二步 C：remove 流程

从 `$ARGUMENTS` 解析 `<id>`；未提供时通过 AskUserQuestion 一问（动态选项从 types-list 生成）。

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py types-remove "$WS_ROOT" "<id>"
```

成功：stdout 为 JSON `{"removed": "<id>"}`，对用户渲染：
```
已删除类型：<id>
同时已从所有 templates.applies_to 中移除对 <id> 的引用。
```

失败（exit 2）：透传 stderr `ERROR:` 消息并 exit 2。常见错误：
- `type <id> 不存在`
- `type <id> 被以下会议引用: <会议列表>` → 用户需先修改引用它的会议 `meta.interviewee_type` 或删除会议

### 第三步：输出引导块

add / remove 完成后输出静态引导块：

```markdown
---
## 下一步

推荐: /mint:types list
原因: 查看当前工作区所有类型及其使用情况

其他选择:
- /mint:templates add: 为新类型绑定访谈提纲
- /mint:templates list: 查看提纲注册表
- /mint:next: 查看当前会议下一步建议

获取引导: /mint:next
```

list 完成后输出：

```markdown
---
## 下一步

推荐: /mint:templates list
原因: 查看提纲注册表并核对 applies_to 映射

其他选择:
- /mint:types add: 继续添加类型
- /mint:types remove <id>: 精简不用的类型
- /mint:next: 查看当前会议下一步建议

获取引导: /mint:next
```

## 参考文档

- `{MINT_REF}/types-templates.md` — ID 约定、预设映射、引用完整性规则
- `{MINT_REF}/workspace-schema.md` — workspace.yaml schema（含 interviewee_types[] 字段）
- `{MINT_REF}/meta-schema.md` — meta.yaml schema（interviewee_type 字段）

## 异常处理

| 情况 | 处理 |
|------|------|
| 工作区未初始化 | 输出 NEG-01 错误（含"未初始化"和"mint:init"），exit 1 |
| scenario != interview | 透传 meta_io stderr `types 管理仅 interview 场景可用`，exit 2 |
| id 重复 | 透传 stderr `type id 已存在`，exit 2 |
| id 格式非法 | 透传 stderr `id 非法`，exit 2 |
| remove 被引用 | 透传 stderr `被以下会议引用`，exit 2 |
| AskUserQuestion 被用户取消 | 不写入 workspace.yaml，输出已取消消息 + exit 0 |

## 非目标（禁止扩展）

- 不支持 rename（改 id 需手工编辑 workspace.yaml）
- 不支持 meeting 场景下使用（PRD 9.7）
- 不做批量导入（一次一个 type；批量走升级脚本）
- 不直接修改 templates 表（通过 --default-template 仅引用存在的 tpl；templates CRUD 走 /mint:templates）
