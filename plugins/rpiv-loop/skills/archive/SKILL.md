---
name: rpiv-loop:archive
description: "归档已完成的过程文件"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
version: 2.1.0
---

# Archive: 归档过程文件

将已完成(status=completed)的过程文件移动到归档目录,保持工作目录清爽。

## 用法

```bash
# 归档所有已完成的文件
/archive all

# 归档指定特性的所有相关文件
/archive feature-name

# 归档指定文件
/archive path/to/file.md
```

## 执行逻辑

### 模式 1: 归档所有已完成文件 (`/archive all`)

1. 扫描以下位置的所有 .md 文件:
   - `rpiv/requirements/`
   - `rpiv/plans/`
   - `rpiv/validation/`
   - `rpiv/todo/`
   - `rpiv/` 根目录下匹配 `brainstorm-summary-*.md` 和 `research-*.md` 的辅助文件
2. 读取每个文件的 frontmatter
3. 筛选出 status=completed 或 status=superseded 的文件
4. 对每个文件执行归档操作(见下方)
5. 生成归档报告

### 模式 2: 归档特性相关文件 (`/archive feature-name`)

1. 在以下位置查找匹配 `*-{feature-name}.md` 的文件:
   - `rpiv/requirements/prd-{feature-name}.md`
   - `rpiv/plans/plan-{feature-name}.md`
   - `rpiv/validation/*-{feature-name}.md`
   - `rpiv/brainstorm-summary-{feature-name}.md`（辅助文件）
   - `rpiv/research-{feature-name}.md`（辅助文件）
   - `rpiv/todo/*-{feature-name}.md`（todo 文件）
2. 读取每个文件的 frontmatter
3. 筛选出 status=completed 或 status=superseded 的文件
4. 对每个文件执行归档操作(见下方)
5. 如果某些文件 status 不是 completed,报告警告
6. 生成归档报告

### 模式 3: 归档指定文件 (`/archive path/to/file.md`)

1. 读取指定文件
2. 检查是否有 frontmatter
3. 检查 status,按以下规则处理:
   - `completed` → 正常归档
   - `open` / `pending` → **直接拒绝**,输出: `⛔ 无法归档: {文件名} 状态为 {status}，未完成的条目不能归档。请先完成处理并将状态更新为 completed，再执行归档。`
   - `in-progress` → 询问用户是否强制归档（可能是已废弃的任务）
4. 执行归档操作(见下方)
5. 生成归档报告

## 归档操作

对单个文件执行以下步骤:

1. **创建归档目录**(如果不存在):
   ```bash
   mkdir -p rpiv/archive
   ```

2. **检查重名冲突**:
   - 检查 `rpiv/archive/` 中是否已存在同名文件
   - 如果存在,生成带时间戳的新文件名:
     ```
     原文件名: prd-feature.md
     新文件名: prd-feature.20260128_103000.md
     ```

3. **更新文件 frontmatter**:
   - 修改 status 为 archived
   - 设置 archived_at 为当前时间戳
   - 更新 updated_at 为当前时间戳

4. **移动文件**:
   ```bash
   mv {source-path} rpiv/archive/{destination-name}
   ```

5. **验证移动成功**:
   - 检查目标文件是否存在
   - 检查源文件是否已删除

## 归档报告

格式:
```markdown
## 归档报告 - {YYYY-MM-DD HH:MM:SS}

### 成功归档 ({count} 个文件)

- [ archived ] prd-feature.md
  - 原路径: rpiv/requirements/prd-feature.md
  - 归档路径: rpiv/archive/prd-feature.md
  - 创建时间: 2026-01-25 10:00:00
  - 归档时间: 2026-01-28 10:30:00

- [ archived ] plan-feature.md
  - 原路径: rpiv/plans/plan-feature.md
  - 归档路径: rpiv/archive/plan-feature.md
  - 创建时间: 2026-01-26 14:00:00
  - 归档时间: 2026-01-28 10:30:00

### 跳过的文件 ({count} 个)

- [ ⛔ open ] chrome-extension-bug.md
  - 原因: 未解决的问题不能归档,请先解决并更新状态为 completed

- [ pending ] prd-another-feature.md
  - 原因: 状态为 pending,未完成

- [ in-progress ] plan-work-in-progress.md
  - 原因: 状态为 in-progress,正在进行中

### 重命名的文件 ({count} 个)

- [ renamed ] prd-feature.md → prd-feature.20260128_103000.md
  - 原因: archive 目录已存在同名文件

### 错误 ({count} 个)

- [ error ] invalid-file.md
  - 错误: 文件不存在或无法读取

---

总计: 成功 {成功数} | 跳过 {跳过数} | 重命名 {重命名数} | 错误 {错误数}
```

## 错误处理

1. **文件不存在**: 报告错误,继续处理其他文件
2. **无权限**: 报告错误,继续处理其他文件
3. **frontmatter 格式错误**: 报告警告,跳过该文件
4. **移动失败**: 报告错误,回滚 frontmatter 更改

## 注意事项

1. 归档操作不可逆(文件会从工作目录移除)
2. 归档前建议先运行 `/rpiv-loop:flow-status` 确认文件状态
3. 归档后的文件仍可通过 Git 历史查看原始版本
4. 只归档有 frontmatter 的文件,旧文件保持不变
