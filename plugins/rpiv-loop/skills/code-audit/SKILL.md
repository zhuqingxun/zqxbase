---
name: rpiv-loop:code-audit
description: >-
  对指定目录/模块进行全量代码审计（不依赖 git diff）。支持 5 个维度的并行审查，置信度评分过滤误报，高严重度问题自动评估爆炸半径。
allowed-tools: Read, Glob, Grep, Bash, Edit, Write
version: 2.1.6
---

对指定目录进行全量代码审计。

## 参数解析

从 `$ARGUMENTS` 中解析：

- **第一个参数**（必填）：目标目录路径（如 `neuromem/services/`、`backend/app/api/`）
- **第二个参数**（可选）：审查维度，支持中英文，以下等价：
  - `logic` | `逻辑` — 逻辑正确性
  - `security` | `安全` — 安全漏洞
  - `performance` | `性能` — 性能问题
  - `architecture` | `架构` — 架构与设计
  - `integration` | `集成` — 集成与环境兼容性
  - 逗号分隔组合：`logic,security` 或 `逻辑,安全`（中英文可混用）
  - 不提供时默认全量审查（5 个维度全部执行）

**示例：**

```
/code-audit neuromem/services/                    # 全量审查
/code-audit neuromem/services/ architecture       # 仅架构深度审查
/code-audit neuromem/services/ 架构               # 同上（中文）
/code-audit backend/app/api/ logic,security       # 逻辑+安全深度审查
/code-audit backend/app/api/ 逻辑,安全            # 同上（中文）
```

## 执行流程

### Phase 0：上下文收集

1. 读取项目根目录的 `CLAUDE.md`、`README.md`（如果存在）
2. 读取目标目录下的 `CLAUDE.md`（如果存在）
3. 扫描 `docs/` 目录中的编码规范文件（如果存在）
4. 记录项目使用的语言、框架、编码规范
5. **运行环境识别**：从 CLAUDE.md 和项目配置（pyproject.toml、package.json、Dockerfile 等）中识别目标运行环境（Windows/macOS/Linux/跨平台），标记为 `cross_platform` 如果代码需在多平台运行
6. **Git 配置检查**：检查 `.gitattributes` 是否存在、是否配置了行尾符规则（`* text=auto` 等），记录对文件内容的潜在影响
7. 如果 `cross_platform = true`，在 Phase 2 的逻辑审查和集成审查中自动激活跨平台兼容性检查项

### Phase 1：文件发现

1. 扫描目标目录，列出所有源代码文件（排除 `.venv/`、`node_modules/`、`__pycache__/`、`.git/`、`dist/`、`build/`）
2. 按文件类型统计（`.py`、`.ts`、`.js`、`.tsx`、`.jsx` 等）
3. 输出文件清单供后续 Agent 使用

### Phase 2：审查执行

根据参数决定执行模式：

#### 全量模式（无第二参数）

启动 **5 个并行 Agent**，每个 Agent 接收完整文件清单和项目上下文（含 Phase 0 的环境信息），各自独立完整阅读每个文件后审查：

**Agent 1 — 逻辑审查（基础）：**
- 边界条件错误（差一、空集合、零值）
- 竞争条件和并发问题
- 错误处理缺失或不当（吞异常、裸 except）
- 空值/None 处理不当
- 条件判断逻辑错误
- **隐式假设挑战**：
  - 字节/字符串比较操作：两端数据是否可能有不同的编码或行尾符（CRLF vs LF）？是否需要归一化后再比较？
  - 文件 I/O 选择：`read_bytes()` vs `read_text()` 是否匹配使用场景？跨平台（Windows CRLF / Unix LF / Git autocrlf）是否影响结果？
  - 时间戳比较：mtime 在 git clone/pull 后是否可靠？不同文件系统的精度差异是否影响判断？
- **数据流对称性**：
  - 当两个数据源的输出用于比较（`==`、`!=`、diff）时，追溯两端的完整变换链，检查是否经过了相同的预处理管道（过滤、剥离、归一化、编码转换）
  - 特别关注：一端经过 parse/split/transform 处理，另一端直接 read 的模式——极易产生不对称

**Agent 2 — 安全审查（基础）：**
- SQL 注入、命令注入
- XSS 漏洞
- 硬编码密钥、API Key、密码
- 权限检查缺失
- 用户输入未验证/未转义

**Agent 3 — 性能审查（基础）：**
- N+1 查询模式
- 内存泄漏（未关闭资源、无界数据结构）
- 热路径上的阻塞操作
- 不必要的重复计算或 I/O
- 可并行但串行执行的操作

**Agent 4 — 架构审查（基础）：**
- SOLID 原则违反（特别是单一职责和依赖倒置）
- 层级穿透（跨层直接访问）
- 循环依赖
- 过度耦合（God Object、超长参数列表）
- 抽象泄漏

**Agent 5 — 集成与环境审查（基础）：**
- **跨平台兼容性**：文件路径分隔符、行尾符（CRLF/LF）、编码、大小写敏感性在目标平台上是否一致
- **外部数据假设**：代码对外部输入（文件内容、API 返回、环境变量）的格式假设是否在所有运行环境中成立
- **配置/列表完备性**：硬编码的排除列表、白名单、映射表是否覆盖了项目中已知的所有实体。**必须用 Glob/ls 实际扫描目标目录，对比列表中的条目和实际存在的目录/文件，报告"列表中有但目录中没有"和"目录中有但列表中没有"的差异**
- **组件间契约**：函数 A 的输出被函数 B 消费时，A 的输出格式是否与 B 的输入预期一致（关注编码、分隔符、是否含 metadata/标记行）
- **环境依赖**：代码是否依赖特定的 git 配置（autocrlf）、文件系统特性（大小写）、shell 环境（PATH）、运行时版本

每个 Agent 返回格式：

```yaml
issues:
  - severity: critical|high|medium|low
    confidence: 0-100
    file: "path/to/file.py"
    line: 42
    issue: "一行描述"
    detail: "为什么这是问题"
    suggestion: "如何修复（含具体代码建议）"
```

#### 单项模式（指定维度）

启动 **1 个 Agent**，执行指定维度的**深度审查**。深度模式在基础检查项之上，额外增加专项深度检查：

**logic 深度模式（基础 + 额外）：**
- + 状态机遗漏转换
- + 异常路径完整性（每个 try 的所有 except 分支是否合理）
- + 资源泄漏（文件句柄、数据库连接、锁未释放）
- + 幂等性和重入安全
- + 并发原语误用（死锁、活锁、饥饿风险）
- + **比较操作审计**：对代码中所有 `==`、`!=`、diff、compare 操作，追溯两端数据的完整变换链，验证变换链的对称性
- + **输入域枚举**：对关键输入（文件内容、API 响应），列举其在不同运行环境中可能的变体（编码、格式、行尾符），评估代码是否处理了所有变体

**security 深度模式（基础 + 额外）：**
- + 认证/授权绕过路径（是否存在未保护的端点或逻辑分支）
- + 序列化/反序列化风险（pickle、yaml.load、JSON 注入）
- + 时序攻击（密码比较、token 验证）和 TOCTOU
- + 日志中的敏感信息泄露（密码、token、PII 写入日志）
- + 依赖链中的已知漏洞模式

**performance 深度模式（基础 + 额外）：**
- + 缓存策略合理性（缓存命中率、过期策略、缓存击穿）
- + 并发/异步优化机会（可 await gather 但逐个 await 的场景）
- + 各层数据序列化开销（频繁 JSON encode/decode、大对象深拷贝）
- + 连接池和资源复用（是否每次新建连接/session）
- + 批量 vs 逐条操作模式（循环内单条 INSERT、逐条 API 调用）

**architecture 深度模式（基础 + 额外）：**
- + 模块职责边界清晰度（单个模块是否承担过多职责）
- + API 设计一致性（命名风格、参数风格、返回值结构是否统一）
- + 依赖方向合理性（高层是否依赖低层，是否存在逆向依赖）
- + 抽象层次是否恰当（过度抽象或抽象不足）
- + 关注点分离程度（业务逻辑是否混入基础设施代码）
- + 可测试性评估（是否有难以 mock 的全局状态或紧耦合）

**integration 深度模式（基础 + 额外）：**
- + **端到端数据流追踪**：选择 2-3 个核心数据流，从输入到输出完整追踪，在每个变换节点检查格式/编码是否保持一致
- + **排除/包含列表全量扫描**：对所有硬编码列表（排除目录、文件类型、映射表），用 Glob 扫描实际文件系统，生成覆盖率报告
- + **Git/文件系统交互审计**：检查所有 git 命令调用和文件系统操作对 autocrlf、core.eol、case sensitivity 的依赖
- + **隐式契约文档化**：识别代码中未明确文档化的隐式假设（如"输入文件一定是 UTF-8""远端和本地行尾符一致"），标记为 medium 风险

组合模式（如 `logic,security`）：启动对应数量的并行 Agent，每个执行对应维度的深度模式。

### Phase 3：汇总与过滤

1. 收集所有 Agent 的发现
2. 去重：同一 file:line 被多个 Agent 报告的，合并为最高严重度
3. **置信度过滤**：仅保留 `confidence >= 75` 的问题进入正式报告，低于 75 的归入"低置信度附录"
4. **爆炸半径评估**：对 `severity = critical 或 high` 的问题，使用 Grep 搜索该函数/类/方法在项目中的所有引用方，记录到 `blast_radius` 字段
5. 按严重度排序：critical → high → medium → low

### Phase 4：健康度评分

根据审查发现计算健康度评分：

- 每个维度独立评分 0-100：
  - 起始 100 分
  - 每个 critical 扣 20 分
  - 每个 high 扣 10 分
  - 每个 medium 扣 5 分
  - 每个 low 扣 2 分
  - 最低 0 分
- 总分 = 各维度评分的加权平均（全量模式 5 维度均等权重；单项模式只有该维度）
- 等级：A(90-100) B(75-89) C(60-74) D(40-59) F(0-39)

## 输出格式

保存到 `rpiv/validation/code-audit-{kebab-case-target-name}.md`

- 如果 `rpiv/validation/` 目录不存在则创建
- `{kebab-case-target-name}` 从目标目录路径生成（如 `neuromem-services`、`backend-app-api`）

```markdown
---
description: "代码审计: {target}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
---

# 代码审计: {target}

## 健康度: {等级} ({总分}/100)

| 维度 | 评分 | 说明 |
|------|------|------|
| 逻辑正确性 | {分数} | {一句话总结} |
| 安全性 | {分数} | {一句话总结} |
| 性能 | {分数} | {一句话总结} |
| 架构 | {分数} | {一句话总结} |
| 集成与环境 | {分数} | {一句话总结} |

**统计：**
- 扫描文件数：{N}
- 发现问题数：{N}（critical: {n}, high: {n}, medium: {n}, low: {n}）
- 过滤低置信度：{N} 个

## 发现的问题

### Critical

severity: critical
confidence: {0-100}
status: open
file: {path/to/file.py}
line: {行号}
issue: {一行描述}
detail: {为什么这是问题}
suggestion: |
  {如何修复，含具体代码建议}
blast_radius: |
  被 {N} 处调用：
  - {caller_file}:{line}
  - {caller_file}:{line}

### High

{同上格式}

### Medium

{同上格式}

### Low

{同上格式}

## 低置信度附录

以下问题置信度 < 75，可能是误报，供参考：

{同上格式，但标注 confidence 分数}
```

如果未发现任何问题：

```markdown
## 健康度: A (100/100)

代码审计通过。未检测到技术问题。
```

## 重要提示

- 每个 Agent 必须**完整阅读**目标文件（使用 Read 工具），不能只读片段
- 专注真正的 bug 和风险，不是风格偏好
- 每个问题必须有具体行号和可操作的修复建议
- 安全问题（密钥泄露、注入）标记为 CRITICAL
- 置信度评分标准：
  - 90-100：确定是真实问题，有明确证据
  - 75-89：高度可能是问题，上下文支持判断
  - 50-74：可能是问题，但也可能有合理理由
  - 0-49：不确定，可能是误报
- 输出报告兼容 `code-review-fix` 流程（`status: open` 字段），修复时使用 `/rpiv-loop:code-review-fix`

## Deferred 问题跟踪文件

当审计报告中的 critical/high 问题被标记为 deferred 时，必须在 `rpiv/todo/` 中创建对应的跟踪文件。文件格式**必须遵循 `record` 技能的标准模板**：

```markdown
---
title: "{问题标题}（审计 {ID}）"
type: issue
status: open
priority: high|medium
source: rpiv/validation/{audit-report-name}.md#{ID}
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
---

# {问题标题}

## 问题现象

{从审计报告中提取的问题描述}

## 根本原因

{如果审计已分析出原因则填写，否则写"待分析"}

## 影响范围

{受影响的文件和模块}

## 已知 Workaround

{如果有临时解决方案则填写，否则写"无"}

## 已尝试的方案

无

## 参考

- 审计报告：{source 路径}
```

**关键要求**：
- 必须使用 `title`（不是 `description`）
- 必须包含 `type: issue`
- 文件名格式：`rpiv/todo/fix-{kebab-case-name}.md`
