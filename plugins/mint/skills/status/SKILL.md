---
name: mint:status
description: >-
  MINT 状态查看——读取 meta.yaml 展示处理进度、质量评分、修订历史和阻塞项，支持单会议聚焦与工作区全景两个视野，以及中表/详表两个详细度。
  当用户说"看看进度""处理到哪了""status""状态""工作区全景""详细状态"时触发。
argument-hint: "[<工作目录>] [--detail] [--workspace]"
allowed-tools: Read, Bash, Glob, Grep, AskUserQuestion
version: 2.1.6
---


# MINT 状态查看（Status）

> **`{MINT_SCRIPTS}` / `{MINT_REF}` 路径约定**：分别指 mint 插件的 `scripts/` 和 `references/` 目录。首次引用时通过
> `Glob("**/plugins/mint/scripts/meta_io.py")` 定位，多结果时优先非 `marketplaces/` 路径（私有开发版）。

读取 `meta.yaml` / `.mint/workspace.yaml`，以表格形式展示处理进度、质量评分、修订历史和阻塞项。支持四种模式覆盖「聚焦/全景」× 「中表/详表」。

## 用法

```
/mint:status [<工作目录>] [--detail] [--workspace]
```

### 参数

| 参数 | 说明 |
|------|------|
| `<工作目录>` | 可选，会议子目录路径。未指定时按 cwd 和 workspace.yaml 推断 |
| `--detail` | 输出详表（追加 quality 分数、产物文件清单、blocker 详述、修订历史） |
| `--workspace` | 输出工作区全景（忽略单会议聚焦，强制扫描工作区所有会议） |

`--detail` 与 `--workspace` 可叠加：

| 组合 | 输出模式 |
|------|---------|
| 默认 | 单会议中表 |
| `--detail` | 单会议详表 |
| `--workspace` / cwd 在工作区根 | 工作区全景中表 |
| `--workspace --detail` | 工作区全景详表 |

## 工作流程

### 第一步：解析模式

1. 读取参数 `<工作目录>` / `--detail` / `--workspace`
2. 定位工作区根：
   ```bash
   uv run --script {MINT_SCRIPTS}/meta_io.py find-workspace-root
   ```
   返回 exit 1 时：输出未初始化错误并结束：
   ```
   当前目录不在 MINT 工作区中。请先运行 /mint:init 初始化工作区。
   ```
3. 模式判定（优先级从高到低）：
   - `--workspace` 传入 → 工作区全景
   - 显式 `<工作目录>` 传入 → 单会议
   - cwd 有 meta.yaml → 单会议（工作目录 = cwd）
   - cwd == 工作区根 → 工作区全景
   - 其他 → 兜底全景

### 第二步：加载数据

**单会议模式**：
```bash
uv run --script {MINT_SCRIPTS}/meta_io.py validate-meta "<工作目录>"
```
返回 exit 1 时：提示对应缺失字段（如 `缺少必要字段 current`，PRD NEG-03 断言）并结束。通过后 Read `<工作目录>/meta.yaml`。

**工作区全景模式**：
```bash
uv run --script {MINT_SCRIPTS}/meta_io.py load-workspace "<工作区根>"
uv run --script {MINT_SCRIPTS}/meta_io.py scan-meetings "<工作区根>"
```
得到 workspace intent + 所有会议的聚合视图。

### 第三步：渲染输出

模式对应的模板见下文「输出格式」。

### 第四步：最后一步——更新元数据并输出引导块

仅在单会议模式下执行（工作区全景模式不写任何会议的 meta.yaml）：

```bash
uv run --script {MINT_SCRIPTS}/meta_io.py refresh-last-action "<工作目录>"
uv run --script {MINT_SCRIPTS}/meta_io.py compute-next-hints "<工作目录>"
```

同时 Edit `meta.yaml`：`current.cursor` 保留（status 不改变 cursor）、`current.last_action_desc` 更新为 `"查看状态"`。

然后：
- Read `{MINT_REF}/next-hints-template.md`
- 用 compute-next-hints JSON 填充 `{primary_cmd}` / `{primary_reason}` / `{alternatives_block}`
- `{alternatives_block}` 按每行 `- {cmd}: {when}` 循环展开，空数组输出单行 `- 无`
- 原样输出填充后的模板（保留开头的 `---` 分隔线）

工作区全景模式下，末尾引导简化为一行："查看具体会议: /mint:next <会议名> 或进入会议子目录后 /mint:status"。

## 输出格式

### 模式 1：单会议中表（默认）

```markdown
## MINT 状态：{project}

工作目录：{工作目录}  
创建日期：{created} | 源音频：{source_audio}  
当前游标 (cursor)：{current.cursor} | 最近操作：{current.last_action_desc} ({current.last_action})  
阻塞项：{blockers_count} 项

### 阶段进度

| 阶段 | 状态 | 版本 | 完成时间 |
|------|------|------|---------|
| Transcribe | {图标} {文本} | v{version} | {MM-DD HH:mm} |
| Refine | {图标} {文本} | v{version} | {MM-DD HH:mm} |
| Polish | {图标} {文本} | v{version} | {MM-DD HH:mm} |
| Extract | {图标} {文本} | v{version} | {MM-DD HH:mm} |
```

### 模式 2：单会议详表（`--detail`）

中表之后追加：

```markdown
### 质量评分（Refine）

| 忠实度 | 流畅度 | 一致性 | 清洁度 | 格式 |
|--------|--------|--------|--------|------|
| {fidelity} | {fluency} | {consistency} | {cleanliness} | {format} |

### 产物文件清单

| 阶段 | 文件 | 大小 |
|------|------|------|
| Transcribe | 02_原始稿/{name}_原始稿.md | {bytes} |
| Refine | 03_校对稿/{name}_校对稿.md | {bytes} |
| ... | ... | ... |

### 阻塞项详述

| # | 类型 | 描述 | 建议动作 |
|---|------|------|---------|
| 1 | {type} | {description} | {suggested_action} |

（无阻塞项时输出：`无阻塞项`）

### 修订历史

| # | 时间 | 类型 | 描述 | 影响文件 |
|---|------|------|------|---------|
| 1 | {MM-DD HH:mm} | {type} | {description} | {files_affected} 个 |
```

### 模式 3：工作区全景中表（`--workspace` 或 cwd 在工作区根）

```markdown
## 工作区：{workspace.name}

项目目标：{intent.goal}  
场景：{workspace.scenario} | 期望交付物：{intent.deliverables join ", "}

### 会议全景

| 会议 | cursor | 进度 | 阻塞 | last_action |
|------|--------|------|------|-------------|
| 01_张三 | extract | 4/4 ✓ | 0 | {MM-DD HH:mm} |
| 02_屈卓 | refine | 2/4 | 0 | {MM-DD HH:mm} |
| 03_李四 | transcribe | 1/4 | 0 | {MM-DD HH:mm} |

共 N 个会议，completed X 个 / in-progress Y 个 / pending Z 个
```

进度列 `X/4` 为已完成阶段数（transcribe/refine/polish/extract），达到 4/4 追加 ✓。

### 模式 4：工作区全景详表（`--workspace --detail`）

全景中表之后追加：

```markdown
### 质量评分总览

| 会议 | 忠实度 | 流畅度 | 一致性 | 清洁度 | 格式 |
|------|--------|--------|--------|--------|------|
| 01_张三 | 95 | 92 | 95 | 93 | 100 |
| 02_屈卓 | -- | -- | -- | -- | -- |

### 阻塞项聚合

| 会议 | # | 类型 | 描述 |
|------|---|------|------|
| 02_屈卓 | 1 | ambiguity | "爱学"公司名还是产品名 |

（无阻塞项时输出：`所有会议均无阻塞项`）
```

## 状态图标映射

| status | 图标 | 文本 |
|--------|------|------|
| completed | [DONE] | 完成 |
| in_progress / running | [....] | 进行中 |
| failed | [FAIL] | 失败 |
| pending | [----] | 待处理 |

## 与 mint:next 的职责区分

- **status**：状态快照。描述「当前是什么」，含 quality 分数、产物文件清单、blocker 详述。不做推荐。
- **next**：决策推荐。描述「下一步该做什么」，全景表仅有 cursor/progress/blocker 计数 + 整体推荐理由。

## 边界规则

- **只读操作**：status 不修改任何产物文件。单会议模式会更新 `meta.yaml.current.last_action_desc` 和 `next_hints`（属于元数据刷新，不算内容修改）
- **meta.yaml 字段缺失必须报错**：遵循 PRD 2.7 原则，不静默补默认值（NEG-02/NEG-03 断言）
- **时间显示一致**：所有时间统一 `MM-DD HH:mm` 格式
- **全景模式不访问单会议产物文件**：只读各 meta.yaml，避免 IO 膨胀
