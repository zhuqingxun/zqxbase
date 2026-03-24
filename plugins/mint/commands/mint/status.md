---
description: MINT 状态查看——读取 meta.yaml 展示当前会议处理进度、质量评分和修订历史。
argument-hint: "[工作目录路径]"
---


# MINT 状态查看（Status）

读取工作目录的 meta.yaml，以表格形式展示处理进度、质量评分和修订历史。

## 用法

```
/mint:status [工作目录路径]
```

如果未指定工作目录，按以下优先级定位：
1. 当前对话上下文中有明确的工作目录 -> 用该目录
2. 用户提到人名或会议名 -> 尝试在常用工作路径下定位
3. 都没有 -> 通过 AskUserQuestion 询问用户指定

## 工作流程

### 第一步：定位并读取 meta.yaml

1. 确定工作目录路径
2. Read `{工作目录}/meta.yaml`
3. 如果 meta.yaml 不存在，输出提示信息并结束：
   ```
   未找到 meta.yaml。此目录尚未初始化 MINT 流水线。
   请先运行 /mint 或 /mint:transcribe 开始处理。
   ```

### 第二步：解析状态数据

从 meta.yaml 中提取：
- `project` — 项目名称
- `created` — 创建日期
- `source_audio` — 源音频文件
- `stages` — 各阶段状态
- `revisions` — 修订历史

### 第三步：生成状态报告

按以下格式输出：

```markdown
## MINT 处理状态：{project}

创建日期：{created} | 源音频：{source_audio}

### 阶段进度

| 阶段 | 状态 | 版本 | 完成时间 | 参数 |
|------|------|------|---------|------|
| Transcribe | {状态图标} {状态文本} | v{version} | {完成时间} | {参数摘要} |
| Refine | {状态图标} {状态文本} | v{version} | {完成时间} | {参数摘要} |
| Polish | {状态图标} {状态文本} | v{version} | {完成时间} | {参数摘要} |
| Extract | {状态图标} {状态文本} | v{version} | {完成时间} | {参数摘要} |
```

#### 状态映射

| status 值 | 图标 | 文本 |
|-----------|------|------|
| completed | [DONE] | 完成 |
| running | [....] | 进行中 |
| failed | [FAIL] | 失败 |
| pending | [----] | 待处理 |

#### 参数摘要格式

将 params 对象压缩为可读的单行文本：
- Transcribe: `{model}, {speakers} speakers`
- Refine: `{mode}, {model}`
- Polish: `{model}`
- Extract: `source: {source}, {intent_depth} intent`

未执行的阶段（pending）参数列显示 `--`。

### 第四步：质量评分（如有）

如果 Refine 阶段有 quality 数据，追加质量评分表：

```markdown
### 质量评分（Refine）

| 忠实度 | 流畅度 | 一致性 | 清洁度 | 格式 |
|--------|--------|--------|--------|------|
| {fidelity} | {fluency} | {consistency} | {cleanliness} | {format} |
```

### 第五步：修订历史（如有）

如果 revisions 列表非空，追加修订历史：

```markdown
### 修订历史

| # | 时间 | 类型 | 描述 | 影响文件 |
|---|------|------|------|---------|
| 1 | {时间} | {type} | {description} | {files_affected} 个 |
| 2 | {时间} | {type} | {description} | {files_affected} 个 |
```

时间格式：`MM-DD HH:mm`（省略年份，当年内更直观）。

### 第六步：快捷操作提示

报告末尾附上可用操作提示：

```markdown
### 可用操作

- `/mint:patch <纠错>` — 修正错字并批量替换
- `/mint:revise <指令>` — 定向修订内容
- `/mint --from {下一待处理阶段}` — 继续未完成的阶段
```

根据当前状态动态调整提示内容（如所有阶段都已完成，则不显示 `--from` 提示）。

## 边界规则

- **只读操作**：status 不修改任何文件
- **meta.yaml 是唯一数据源**：不扫描文件系统推断状态，完全依赖 meta.yaml
- **优雅降级**：meta.yaml 中缺少某些字段时，对应列显示 `--` 而非报错
- **时间显示一致**：所有时间统一使用 `MM-DD HH:mm` 格式
