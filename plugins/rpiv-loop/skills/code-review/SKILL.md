---
name: rpiv-loop:code-review
description: >-
  在提交前运行的技术代码审查，用于质量和错误检查
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
version: 2.2.0
---

对最近更改的文件执行技术代码审查。

## 核心原则

审查理念：

- 简单是终极的复杂 - 每一行都应该证明其存在的价值
- 代码被阅读的次数远多于编写 - 优化可读性
- 最好的代码往往是你没有写的代码
- 优雅源于意图的清晰和表达的简洁

## 审查内容

首先收集代码库上下文以了解代码库标准和模式。

首先检查：

- CLAUDE.md
- README.md
- /core 模块中的关键文件
- /docs 目录中记录的标准

在充分理解后

运行这些命令：

```bash
git status
git diff HEAD
git diff --stat HEAD
```

然后检查新文件列表：

```bash
git ls-files --others --exclude-standard
```

完整阅读每个新文件。完整阅读每个更改的文件（不仅仅是 diff）以理解完整上下文。

对于每个更改的文件或新文件，分析：

1. **逻辑错误**
   - 差一错误
   - 不正确的条件判断
   - 缺少错误处理
   - 竞争条件

2. **安全问题**
   - SQL 注入漏洞
   - XSS 漏洞
   - 不安全的数据处理
   - 暴露的密钥或 API 密钥

3. **性能问题**
   - N+1 查询
   - 低效的算法
   - 内存泄漏
   - 不必要的计算

4. **代码质量**
   - 违反 DRY 原则
   - 过于复杂的函数
   - 命名不当
   - 缺少类型提示/注解

5. **遵守代码库标准和现有模式**
   - 遵守 /docs 目录中记录的标准
   - 代码检查、类型和格式标准
   - 日志记录标准
   - 测试标准

6. **删测试资产覆盖核对**（当 diff 含测试文件/测试资产删除时强制）
   - 对每个被删测试，**逐条**列出其断言维度（文本内容 / 几何 / fill / 字号 / 边界 等），不能只看测试名或参数化的 `visual_type` 名
   - 对每个断言维度，核对是否真有替代测试覆盖——**参数化覆盖同名 type ≠ 覆盖该测试所有断言维度**
   - 任一断言维度无替代覆盖 → 标记为问题，要求"先补再删"，缺口补齐前不得删除

## 验证问题是否真实

- 为发现的问题运行特定测试
- 确认类型错误是合法的
- 结合上下文验证安全问题

## 输出格式

将新文件保存到 `rpiv/validation/code-review-{kebab-case-feature-name}.md`

- 如果 `rpiv/validation/` 目录不存在则创建

### 文件格式

文件必须包含 YAML frontmatter 和内容：

```markdown
---
description: "代码审查报告: {feature-name}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
---

# 代码审查报告

{审查内容}
```

**Frontmatter 字段说明：**
- `description`: 文件描述
- `status`: 文件状态，新创建时固定为 `pending`
- `created_at`: 创建时间戳，ISO 8601 格式
- `updated_at`: 更新时间戳，创建时与 created_at 相同
- `archived_at`: 归档时间戳，创建时固定为 `null`

**统计：**

- 修改的文件：0
- 添加的文件：0
- 删除的文件：0
- 新增行：0
- 删除行：0

**对于每个发现的问题：**

```
severity: critical|high|medium|low
status: open
file: path/to/file.py
line: 42
issue: [一行描述]
detail: [解释为什么这是问题]
suggestion: [如何修复]
```

> `status` 字段取值：`open`（新建时固定）、`fixed`（已修复）、`skipped`（有意跳过，需附理由）。由 code-review-fix 流程在修复完成后回写。

如果未发现问题："代码审查通过。未检测到技术问题。"

## 完成后续

审查产出后，按结论闭合**本审查文件**的 frontmatter `status`（填补干净审查的状态闭合路径——干净审查不会触发 `code-review-fix`，必须由本技能自闭合，否则文件永久卡在 `pending`）：

- **干净通过**（输出"代码审查通过。未检测到技术问题。"，或仅余 low / by-design 等**无需 `code-review-fix` 介入**的观察）：不会有后续修复流程被触发，**由本技能直接闭合**——将审查文件 `status` 改为 `completed`，同步 `updated_at`。
- **发现需修复的问题**（存在 `status: open` 的 critical / high / medium）：保持 `status: pending`，提示用户运行 `/rpiv-loop:code-review-fix <审查文件路径>`，由该流程修复后翻 `completed`（见 code-review-fix SKILL step 4 闭环校验）。

> 单一职责说明：两条路径**互斥**（一次审查要么干净、要么有问题），不会双写 status，与 `references/frontmatter-spec.md` 职责表 code-review 行一致。

## 重要提示

- 要具体（行号，不要模糊的抱怨）
- 专注于真正的错误，而不是风格
- 建议修复方法，不要只是抱怨
- 将安全问题标记为 CRITICAL
