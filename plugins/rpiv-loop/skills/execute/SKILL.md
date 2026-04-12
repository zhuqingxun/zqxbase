---
name: rpiv-loop:execute
description: 执行实施计划
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Skill
version: 2.1.4
---

# Execute: 从计划实施

## 要执行的计划

读取计划文件：`$ARGUMENTS`

## 执行指令

### 0. 前置处理

**在执行前管理计划文件状态：**

1. 读取计划文件路径：`$ARGUMENTS`
2. 检查计划文件是否有 YAML frontmatter
3. 如果有 frontmatter，根据当前 status 处理：
   - `pending` → 更新为 `in-progress`，更新 `updated_at`
   - `in-progress` → **可能是上次会话中断**。使用 AskUserQuestion 询问用户：① 继续执行（保持 in-progress）② 重新开始（更新 `updated_at`）
   - `completed` → 提示"此计划已执行完成"，询问用户是否需要重新执行
   - `superseded` → 提示"此计划已被新版本取代"，建议执行新版本
4. 如果没有 frontmatter（旧文件），跳过状态更新

### 1. 阅读和理解

- 仔细阅读整个计划
- 理解所有任务及其依赖关系
- 注意要运行的验证命令
- 审查测试策略

### 2. 按顺序执行任务

对于"逐步任务"中的每个任务：

#### a. 导航到任务
- 识别所需的文件和操作
- 如果修改，阅读现有的相关文件

#### b. 实施任务
- 严格按照详细规范执行
- 保持与现有代码模式的一致性
- 包含适当的类型提示和文档
- 在适当的地方添加结构化日志

#### c. 边做边验证
- 每次文件更改后，检查语法
- 确保导入正确
- 验证类型定义正确

### 3. 实施测试策略

完成实施任务后：

- 创建计划中指定的所有测试文件
- 实施所有提到的测试用例
- 遵循概述的测试方法
- 确保测试覆盖边缘情况

### 4. 运行验证命令

按顺序执行计划中的所有验证命令：

```bash
# 完全按照计划中的指定运行每个命令
```

如果任何命令失败：
- 修复问题
- 重新运行命令
- 只有在通过时才继续

### 5. 最终验证

完成前：

- ✅ 计划中的所有任务已完成
- ✅ 所有测试已创建并通过
- ✅ 所有验证命令通过
- ✅ 代码遵循项目约定
- ✅ 文档已根据需要添加/更新

## 输出报告

**硬规则：无新鲜验证证据，不得声称任务完成。** 报告中的每个"已完成"声明都必须附带实际运行的验证命令及其输出。禁止使用"应该能工作"、"大概通过了"等模糊措辞——要么有证据证明通过，要么明确标记为未验证。

提供摘要：

### 已完成的任务

对每个任务，提供：
- 任务描述
- 创建/修改的文件（带路径）
- **验证证据**：实际运行的命令和输出（精简关键行即可）

```
任务: CREATE src/new_module.py
文件: src/new_module.py (新建)
验证: `uv run python -c "import new_module"` → 退出码 0，无错误
```

未能验证的任务必须标记 `⚠️ 未验证` 并说明原因。

### 添加的测试
- 创建的测试文件
- 实施的测试用例
- **测试运行输出**（完整的通过/失败结果）

### 验证结果
```bash
# 每个验证命令的完整输出（不是记忆中的，是刚刚执行的）
```

### 准备提交
- 确认所有更改已完成
- 确认所有验证通过（附证据）
- 准备使用 `/commit` 命令

## 完成后续

**所有验证通过后：**

1. 更新计划文件的 frontmatter：
   - status 从 `in-progress` 改为 `completed`
   - 更新 `updated_at` 时间戳为当前时间
2. **执行经验提取**（自包含，不依赖外部技能）：
   - 回溯本次执行中所有失败的工具调用（Bash 报错、文件编辑冲突等）
   - 对每个失败，判断：是一次性问题（环境、网络）还是暴露了可复用的模式（编码规范、框架用法、项目约定）？
   - 如果发现可复用的模式，在输出报告的"建议"章节中明确建议更新哪个文件（项目 CLAUDE.md / 计划模板 / 其他）
   - 这一步不超过 2 分钟，不要过度分析
3. **闭环关联 todo 文件**：
   - 从计划文件名提取 feature-name（如 `plan-foo.md` → `foo`）
   - 扫描 `rpiv/todo/*-{feature-name}.md`（也可用 `grep -rl` 按关键词匹配）
   - 对每个 status=open 或 status=in-progress 的关联 todo 文件：
     - 更新 frontmatter：`status: completed`，更新 `updated_at`
     - 在文件末尾追加简要完成记录：`## 完成记录\n\n通过 /rpiv-loop:execute 执行计划 {plan-file} 完成。时间：{timestamp}`
   - 输出更新了哪些 todo 文件，供用户确认
4. **归档已完成的关联文件**：
   - 扫描以下位置的关联文件：
     - `rpiv/todo/*-{feature-name}.md`（含上一步刚标记为 completed 的）
     - `rpiv/requirements/prd-{feature-name}.md`
     - `rpiv/` 根目录下的 `brainstorm-summary-{feature-name}.md`、`research-{feature-name}.md`
   - 对每个 status=completed 或 status=superseded 的关联文件，执行归档：
     - 更新 frontmatter：status→archived，添加 `archived_at`，更新 `updated_at`
     - 移动到 `rpiv/archive/`（有同名文件则添加时间戳后缀）
     - 验证移动成功（目标存在、源已删除）
   - 对计划文件自身执行相同归档操作
   - 对 status 不是 completed/superseded 的关联文件，在报告中标注警告但不归档
4. 提示用户："执行已完成。计划及关联文件已归档。"
5. 建议下一步："建议 `/clear` 后执行验证流程：`/rpiv-loop:code-review` → `/rpiv-loop:execution-report` → `/rpiv-loop:system-review`"

## 备注

- 如果遇到计划中未解决的问题，请记录它们
- 如果需要偏离计划，请解释原因
- 如果测试失败，修复实施直到它们通过
- 不要跳过验证步骤
- **验证必须是新鲜执行的**：不要依赖之前运行的结果或记忆中的输出。声称完成前，重新运行验证命令并在报告中引用实际输出
