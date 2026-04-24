---
name: mint:templates
description: >-
  MINT 访谈提纲注册表管理——管理工作区级 templates[] 注册表，登记 PDF/Markdown 提纲及其 applies_to 映射。
  支持 add / list / remove 三子命令。
  当用户说"添加提纲""登记模板""templates add""查看提纲""删除提纲""/mint:templates"时触发。
  仅 interview 场景可用；polish 通过 resolve-template 自动选出本表中的条目。
argument-hint: "[add|list|remove] [<id>] [<name>] [<file>] [<applies_to>] [--set-default]"
allowed-tools: Read, Bash, Glob, AskUserQuestion
version: 2.1.6
---

# mint:templates — 访谈提纲注册表管理

> **路径约定**：`{MINT_REF}` = mint 插件 `references/` 目录，`{MINT_SCRIPTS}` = 同级 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/mint/references/types-templates.md")` 定位，多结果时优先非 `marketplaces/` 路径。

管理工作区 `.mint/workspace.yaml` 中的 `templates[]` 注册表。每个 template 记录一份访谈提纲文件（PDF/Markdown 等），并通过 `applies_to` 声明它适用于哪些 `interviewee_types[].id`。

`mint:polish` 的第零步调 `resolve-template` 自动按 `meta.interviewee_type` → `types.default_template_id` 查询本表，无需手工 `--template`。

## 用法

```
/mint:templates add [<id>] [<name>] [<file>] [<applies_to>] [--set-default]
/mint:templates list
/mint:templates remove <id>
```

- 未指定参数时通过 AskUserQuestion 交互补齐。
- `<applies_to>`：逗号分隔的 type id 列表（必须已在 interviewee_types 表中注册）。
- `--set-default`：同时把该 template 设为 `applies_to` 里每个 type 的 `default_template_id`。
- 仅 interview 场景可用。

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

从 `$ARGUMENTS` 剩余 token 解析位置参数 `<id>` / `<name>` / `<file>` / `<applies_to>` 和可选 `--set-default`。

若有字段缺失，调用 **一次** AskUserQuestion 批次补齐（最多 4 问，按需省略）：

- **Qa — name**（仅 name 未提供）
  - question: `提纲的展示名是什么? (可含中文)`
  - header: `提纲名`
  - multiSelect: `false`
  - options（1 项 + 自动 Other，用户基本走 Other 输入自由文本）:
    - label: `跳过` — description: `暂不命名，占位字符串（不推荐）`

- **Qb — file**（仅 file 未提供）
  - 通过 Glob 扫工作区根下的 `*.pdf` / `*.md` / `*.docx`（限一级子目录）作为候选（最多 3 项 + 自动 Other）:
    - label: `<basename>` — description: `<相对路径>`（每个候选一项）

  用户选中后记录**绝对路径或相对工作区根的路径**。`templates-add` CLI 会自动校验 file 存在、按**原文件名**搬到 `.mint/templates/<basename>`（保留中文全角字符）、并把 `workspace.yaml.templates[].file` 写成该相对路径，skill 不需要自己做 mkdir/mv。sanitize 重命名由独立升级脚本 `--sanitize` 负责，不是 templates-add 的行为。

- **Qc — applies_to**（仅 applies_to 未提供）
  先调 `types-list` 取所有 type id。
  - question: `该提纲适用于哪些受访者类型? (可多选)`
  - header: `applies_to`
  - multiSelect: `true`
  - options（动态，最多 4 项；types 数量 > 4 时取前 4 项并让用户后续手工补）:
    - label: `<type-id>` — description: `<type-name>`

- **Qd — set_default**（仅 --set-default 未提供且 applies_to 非空）
  - question: `是否把该提纲设为 applies_to 中每个类型的默认提纲?`
  - header: `设为默认`
  - multiSelect: `false`
  - options（必须恰好 2 项）:
    - label: `是` — description: `推荐：自动回填 types[].default_template_id`
    - label: `否` — description: `仅登记 template，不修改 types 表`

#### A.2 id 规范化

若 id 未提供，由 name 通过 `normalize_id(name, existing_template_ids, prefix="tpl-")` 生成。skill 本体不重实现；直接把 `name` 传给 CLI，让 CLI 内部处理 id 生成也可（但当前 CLI 要求显式 id，skill 层先生成 id 再传）。

最简做法：skill 层用一段 uv run python 调 `normalize_id`：

```bash
ID=$(uv run --with pyyaml python -c "
import sys
sys.path.insert(0, '{MINT_SCRIPTS_DIR}')
from meta_io import normalize_id, load_workspace
from pathlib import Path
ws = load_workspace(Path('$WS_ROOT/.mint/workspace.yaml'))
existing = {t['id'] for t in (ws.get('templates') or []) if isinstance(t, dict)}
print(normalize_id('$NAME', existing, prefix='tpl-'))
")
```

`{MINT_SCRIPTS_DIR}` = `{MINT_SCRIPTS}` 的绝对路径（由 Glob 定位后记录）。

#### A.3 调 CLI 写入

```bash
CMD_ARGS=("$WS_ROOT" "$ID" "$NAME" "$FILE" "$APPLIES_TO")
if [ "$SET_DEFAULT" = "true" ]; then
  CMD_ARGS+=(--set-default)
fi
uv run --script {MINT_SCRIPTS}/meta_io.py templates-add "${CMD_ARGS[@]}"
```

成功：stdout 为 JSON `{"added": {...}, "updated_types": [...]}`，对用户渲染：
```
已添加提纲：<id> (<name>)
文件：<file>
applies_to：<comma-separated>
已回填默认 types：<updated_types | 无>
```

失败（exit 2）：透传 stderr `ERROR:` 消息并 exit 2。常见错误：
- `template id 已存在: <id>`
- `file not found: <path>`（NEG-TT-04）
- `目标文件已存在，拒绝覆盖: .mint/templates/<id>.<ext>`
- `applies_to 不能为空`
- `applies_to 含未注册的 type: <list>`
- `id 非法: <id>，必须匹配 ^[a-z][a-z0-9-]*$`
- `templates 管理仅 interview 场景可用`

### 第二步 B：list 流程

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py templates-list "$WS_ROOT"
```

stdout 为 JSON 数组，每项含 `id / name / file / applies_to`。

渲染表格：

```markdown
## 访谈提纲注册表（{N} 项）

| id | name | file | applies_to |
|----|------|------|------------|
| tpl-internal | 内部提纲 | .mint/templates/tpl-internal.pdf | internal |
| tpl-external | 外部提纲 | .mint/templates/tpl-external.pdf | external |
```

空列表输出：`当前工作区未注册任何 template，建议运行 /mint:templates add 补齐。`

### 第二步 C：remove 流程

从 `$ARGUMENTS` 解析 `<id>`；未提供时通过 AskUserQuestion 一问（动态选项从 templates-list 生成）。

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py templates-remove "$WS_ROOT" "<id>"
```

成功：stdout 为 JSON `{"removed": "<id>", "file": "...", "file_deleted": true|false}`，对用户渲染：
```
已删除提纲：<id>
物理文件：<file>（<已删除 | 未找到>）
```

失败（exit 2）：透传 stderr `ERROR:` 消息并 exit 2。常见错误：
- `template <id> 不存在`
- `template <id> 被以下引用: types=[...]; meetings=[...]` → 引用扫描不短路，types + meetings 引用会被汇总列出；用户需先修改 types 的 default_template_id 或清理会议 polish.params.template_override 后重试

### 第三步：输出引导块

add 完成后：

```markdown
---
## 下一步

推荐: /mint:templates list
原因: 核对新增 template 与 applies_to 映射

其他选择:
- /mint:types list: 查看默认提纲回填情况
- /mint:polish <会议>: 用新提纲跑 polish（自动通过 interviewee_type 匹配）
- /mint:next: 查看当前会议下一步建议

获取引导: /mint:next
```

list / remove 完成后输出类似引导块，推荐 `/mint:types list` 或 `/mint:next`。

## 参考文档

- `{MINT_REF}/types-templates.md` — ID 约定、引用完整性规则、polish 三层兜底
- `{MINT_REF}/workspace-schema.md` — workspace.yaml schema（含 templates[] 字段）
- `{MINT_REF}/meta-schema.md` — polish.params.template_override 字段说明

## 异常处理

| 情况 | 处理 |
|------|------|
| 工作区未初始化 | 输出 NEG-01 错误（含"未初始化"和"mint:init"），exit 1 |
| scenario != interview | 透传 `templates 管理仅 interview 场景可用`，exit 2 |
| id 重复 / 非法 | 透传 stderr，exit 2 |
| applies_to 含未注册 type | 透传 stderr，exit 2 |
| remove 被类型或会议引用 | 透传 stderr `被以下...引用`，exit 2 |
| 物理文件缺失 | templates-remove 宽容通过（`file_deleted: false`） |
| AskUserQuestion 被用户取消 | 不写入 workspace.yaml，输出已取消消息 + exit 0 |

## 非目标（禁止扩展）

- 不支持 rename（改 id 需手工编辑 workspace.yaml）
- 不支持 meeting 场景（PRD 9.7）
- 不做 template 文件内容解析（只当黑盒路径处理；polish 第零步才消费）
- 不支持 `file` 为空（所有 template 都必须有物理文件）
- 不做多 template 选择交互（PRD 9.7：applies_to 多匹配取 type 的 default_template_id 即可）
