---
name: rpiv-loop:validation:code-review-fix
description: >-
  修复手动/AI 代码审查中发现的问题的流程
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
version: 2.1.3
---

我运行/执行了代码审查并发现了这些问题：

代码审查（文件或问题描述）：$1

请逐个修复这些问题。如果代码审查是一个文件，请先完整阅读该文件以了解其中呈现的所有问题。

范围：$2

对于每个修复：
1. 解释哪里出了问题
2. 展示修复方法
3. 创建并运行相关测试以验证

所有修复完成后：

1. 运行 `/rpiv-loop:validation:validate` 以完成修复
2. **回写审查文档闭环**：打开原始代码审查文件，将每个问题的 `status` 更新为以下三种之一（禁止存在无归属的 skipped 状态）：
   - `fixed` — 已修复的问题
   - `wont_fix` — 评估后决定不修复的问题，在 `status` 行下方追加 `wont_fix_reason: [原因]`（如：风格偏好、设计意图、已被其他修复覆盖、影响极低等）
   - `deferred` — 当前无法修复但需要后续跟踪的问题，在 `status` 行下方追加 `deferred_reason: [原因]`，并**必须在 `rpiv/todo/` 下创建对应的待办文件**跟踪
3. **闭环校验**：逐项检查，确保每个问题都有明确结论：
   - 所有 `deferred` 项在 `rpiv/todo/` 下有对应文件
   - 不存在仍为 `open` 或空白 status 的问题
4. 更新审查文件 frontmatter：
   - `status` 更新为 `completed`（所有问题均已 fixed / wont_fix / deferred 即视为完成）
   - `updated_at` 更新为当前时间
5. **闭环关联 todo 文件**：
   - 从审查文件名或修复内容中提取 feature-name
   - 扫描 `rpiv/todo/` 中与本次修复工作相关的 todo 文件（按文件名关键词或 `grep -rl` 内容匹配）
   - 对每个 status=open 且本次修复已完整解决其描述问题的 todo 文件：
     - 更新 frontmatter：`status: completed`，更新 `updated_at`
     - 在文件末尾追加：`## 完成记录\n\n通过 /rpiv-loop:validation:code-review-fix 修复完成。审查文件：{review-file}。时间：{timestamp}`
   - 如果某个 todo 仅被部分解决，不更新状态，但在输出中提示用户
   - 如果没有找到关联 todo 文件，静默跳过（不是所有修复都有对应 todo）
