---
name: mint:init
description: >-
  MINT 工作区初始化命令——在当前目录创建 .mint/workspace.yaml 工作区标识文件，
  通过两轮 AskUserQuestion 引导用户填写 scenario / deliverables / goal（interview 场景追加受访者类型）。
  当用户说"初始化工作区""init""新建 mint 工作区""/mint:init"时触发。
  这是所有 mint 流水线使用的前置步骤：未 init 的目录运行 /mint 或 /mint:next 会报错。
allowed-tools: Read, Write, Bash, AskUserQuestion
version: 2.1.6
---

# mint:init — 工作区初始化

> **路径约定**：`{MINT_REF}` = mint 插件 `references/` 目录，`{MINT_SCRIPTS}` = 同级 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/mint/references/lessons-learned.md")` 定位，多结果时优先非 `marketplaces/` 路径。

## 用法

```
/mint:init
```

在希望作为工作区根的目录下运行（通常就是 cwd）。单次调用无参数，流程结束后该目录下会出现 `.mint/workspace.yaml`。

## 执行流程

### 第一步：前置检查

前置检查任何一项失败都直接报错退出（禁止静默继续）。

1. **当前目录已初始化**：
   ```bash
   test -f "$PWD/.mint/workspace.yaml"
   ```
   若存在 → 输出 `工作区已初始化: $PWD/.mint/workspace.yaml，如需修改请直接编辑` 并 exit 1。

2. **cwd 祖先已属于工作区**：
   ```bash
   uv run --script {MINT_SCRIPTS}/meta_io.py find-workspace-root "$PWD"
   ```
   若 exit 0 且输出的路径不是 `$PWD` → 输出 `当前目录已属于工作区 <祖先路径>，请 cd 到独立目录再初始化` 并 exit 1。

3. **老工作区检测**：
   在 $PWD 一级子目录中查找含 `meta.yaml` 的目录（即 `*/meta.yaml`）：
   ```bash
   ls $PWD/*/meta.yaml 2>/dev/null | head -1
   ```
   若存在且当前目录下无 `.mint/` → 输出 `检测到老工作区（存在含 meta.yaml 的子目录但无 .mint/ 标识），请先运行一次性升级脚本再跑 /mint:init` 并 exit 1。

前置全部通过才进入第二步。

### 第二步：第一轮 AskUserQuestion（Q1 单独）

Q4 仅在 interview 场景触发，而 AskUserQuestion 的 batch 内无条件分支能力，因此拆两轮交互：第一轮先拿到 scenario，第二轮根据 scenario 决定 questions 数组。

调用 **一次** AskUserQuestion，`questions` 数组仅含 Q1：

**Q1 — scenario（单选）**

- question: `本工作区的场景类型是什么?`
- header: `场景类型`
- multiSelect: `false`
- options（必须恰好 2 项）：
  - label: `interview` — description: `主题访谈：有提纲与受访人的一对一/一对多对话`
  - label: `meeting` — description: `一次性多人交流：产品评审/团队周会/决策会议等`

收到返回后，将答案存入变量 `SCENARIO`（值必为 `interview` 或 `meeting`）。

### 第三步：第二轮 AskUserQuestion（Q2/Q3 + interview 追加 Q4）

根据 `SCENARIO` 构造第二轮 `questions` 数组：

- `SCENARIO == "interview"` → `[Q2, Q3, Q4]`（3 问）
- `SCENARIO == "meeting"` → `[Q2, Q3]`（2 问）

一次性调用 AskUserQuestion（单 batch）。

**Q2 — deliverables（多选并集 4 项）**

- question: `希望产出哪些交付物? (可多选, 会按场景自动补齐)`
- header: `交付物`
- multiSelect: `true`
- options（必须 4 项，硬编码并集）：
  - label: `观点分析` — description: `提取受访人的观点、立场与深层意图`
  - label: `行动项` — description: `可执行的下一步任务清单`
  - label: `决议清单` — description: `多人会议中达成的决定事项`
  - label: `要点摘要` — description: `结构化的要点回顾`

说明：Q2 的 options 是两场景并集。过滤与补齐由 `meta_io.py init-workspace` 按 Q1 结果处理。

**Q3 — goal（4 预设 + 自动 Other 兜底）**

- question: `用一句话描述本工作区的项目目标?`
- header: `项目目标`
- multiSelect: `false`
- options（必须恰好 4 项）：
  - label: `输出综合洞察报告` — description: `访谈合集分析，产出跨受访人的综合结论`
  - label: `留存结构化记录` — description: `每场会议产出要点摘要/行动项，不做综合分析`
  - label: `撰写专题分析` — description: `围绕某主题收集观点支撑材料`
  - label: `一次性事项纪要` — description: `单次会议的决议与行动项记录`

Claude Code 会自动附加 Other 让用户填写自定义文本。**禁止**自行把 Other 放进 options 数组。

**Q4 — interviewee_types（仅 interview 场景；多选 + 自动 Other 兜底）**

- question: `本工作区的受访者类型（至少选一个，可用"其他"添加自定义）`
- header: `受访者类型`
- multiSelect: `true`
- options（必须恰好 3 项，硬编码预设；Claude Code 自动附加 Other 兜底）：
  - label: `内部员工` — description: `组织内部人员（部门员工 / 干部 / 技术骨干等）`
  - label: `外部员工 / 服务对象` — description: `供应商 / 客户 / 服务对象 / 合作方`
  - label: `领导层` — description: `高管 / 总监 / 决策层`

说明：
- Q4 至少选 1 项（含 Other 自定义文本）。若为空，进入第四步时报错退出
- Other 的自定义文本若含中文，id 生成会走 normalize_id 报错；这种场景提示用户用英文 label 或后续手工编辑 workspace.yaml

### 第四步：解析答案并写入 workspace.yaml

收到第二轮返回后：

1. **Q2 答案** → 变量 `DELIVERABLES`，用户勾选的 label 组成的逗号分隔字符串（按勾选顺序）
   - 用户可能 0-4 项全选：数量不限（meta_io 会按 scenario 过滤/补齐）
2. **Q3 答案** → 变量 `GOAL`，用户所选 label 或 Other 填写的文本
3. **Q4 答案**（仅 interview 场景）→ 变量 `TYPES_SELECTED`，勾选的 label 列表（含 Other 文本）
   - interview 场景下 `TYPES_SELECTED` 为空 → 报错 `interview 场景至少选一个受访者类型` + exit 1（不写入 workspace.yaml）
   - meeting 场景不构造 `TYPES_SELECTED`

先调用 meta_io.py 的 `init-workspace` 创建基础 workspace.yaml：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py init-workspace "$PWD" "<SCENARIO>" "<GOAL>" "<DELIVERABLES>"
```

参数说明：
- `<SCENARIO>` 必须是 `interview` 或 `meeting`
- `<GOAL>` 原样透传，含空格和中文引号请整个用双引号包裹
- `<DELIVERABLES>` 逗号分隔

成功返回 JSON：`{"workspace_yaml": "<绝对路径>"}`。失败（已存在、scenario 非法）exit 非 0 并在 stderr 输出 `ERROR: ...`。

**interview 场景：循环追加 types**

对 `TYPES_SELECTED` 中每个 label，按以下映射生成 id 后逐个调 `types-add`：

| label | id |
|-------|----|
| `内部员工` | `internal` |
| `外部员工 / 服务对象` | `external` |
| `领导层` | `leader` |
| Other 自定义文本（纯英文） | 对文本做 slug 化：`name.lower()` + 非 `[a-z0-9]` 替换为 `-`，strip 首尾 `-` |
| Other 自定义文本（含中文） | 报错提示用户用英文 label 或手工编辑 workspace.yaml 后退出 |

逐个调用：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py types-add "$PWD" "<id>" "<label>"
```

说明：
- 每次调用独立进程；中途任一调用失败（stderr 含 `ERROR:`）→ 整体失败退出，不尝试回滚已写入的 types（用户可手工编辑 workspace.yaml 清理）
- 中途失败时必须向用户明确报告"init-workspace 已成功但第 N 个 type 追加失败"，避免误以为未 init

meeting 场景：跳过 types 循环（即使用户在 Q4 误选也忽略，不写入 interviewee_types[]）。

### 第五步：验证写入结果

```bash
test -f "$PWD/.mint/workspace.yaml" && grep -q '^  scenario:' "$PWD/.mint/workspace.yaml"
```

interview 场景额外验证：

```bash
grep -q '^interviewee_types:' "$PWD/.mint/workspace.yaml"
```

若任一失败，立即报告错误。

### 第六步：输出引导块

**禁止** 在 init 里调 `compute-next-hints`（此时工作区还没有任何 meeting，meta.yaml 不存在），直接输出静态引导块。

interview 场景（建议先注册提纲再转录）：

```markdown
---
## 下一步

推荐: /mint:templates add <访谈提纲 PDF 路径>
原因: 工作区已初始化含受访者类型，注册提纲后 polish 可自动选中匹配模板

其他选择:
- /mint:types list: 查看已注册的受访者类型
- /mint:transcribe <音频> <会议名>: 不注册提纲也可以直接转录，polish 走无模板模式
- 手动编辑 .mint/workspace.yaml: 调整 intent/goal/deliverables/types

获取引导: /mint:next
```

meeting 场景（保持原文案）：

```markdown
---
## 下一步

推荐: /mint:transcribe <音频路径> <会议名>
原因: 工作区已初始化，开始第一个会议的转录

其他选择:
- /mint:next: 查看引导（工作区无会议时会提示先做 transcribe）
- 手动编辑 .mint/workspace.yaml: 调整 intent/goal/deliverables

获取引导: /mint:next
```

## 参考文档

- `{MINT_REF}/workspace-schema.md` — workspace.yaml schema（含 interviewee_types / templates）
- `{MINT_REF}/scenario-presets.md` — scenario 枚举 + deliverables 过滤规则
- `{MINT_REF}/meta-schema.md` — 会议级 meta.yaml schema（transcribe 阶段写入）
- `{MINT_REF}/types-templates.md` — ID 约定、预设映射、引用完整性规则

## 异常处理

| 情况 | 处理 |
|------|------|
| .mint/workspace.yaml 已存在 | 报错 `工作区已初始化: <路径>` + exit 1（PRD INIT-03 / NEG-04） |
| cwd 祖先已有 .mint/workspace.yaml | 报错 `当前目录已属于工作区 <祖先>` + exit 1 |
| 子目录有 meta.yaml 但无 .mint/ | 报错 `检测到老工作区，请先运行一次性升级脚本` + exit 1 |
| AskUserQuestion 被用户取消 | 不写入 workspace.yaml，输出已取消消息 + exit 0 |
| init-workspace 返回 scenario 非法 | 透传 meta_io stderr，exit 1 |
| interview 场景 Q4 为空 | 报错 `interview 场景至少选一个受访者类型` + exit 1（不写入 workspace.yaml） |
| Q4 Other 自定义含中文无法生成 id | 报错提示用户改用英文 label 或完成 init 后手工编辑 workspace.yaml + exit 1 |
| 循环 types-add 中途失败 | 明确报告 `init-workspace 已成功但第 N 个 type 追加失败`，不自动回滚 |

## 非目标（禁止扩展）

- 不接受命令行参数（scenario/goal/deliverables 必须通过 AskUserQuestion 交互）
- 不自动迁移老工作区的 desensitization_registry.yaml 到 .mint/（由独立升级脚本处理）
- 不创建任何会议子目录（`mint:transcribe` 首次跑会自建）
- 不在末尾调 compute-next-hints（此时无 meta.yaml）
- 不自动注册 templates（由 `/mint:templates add` 单独处理）
- 不为 Other 自定义类型做拼音转换（非 ASCII 直接报错）
