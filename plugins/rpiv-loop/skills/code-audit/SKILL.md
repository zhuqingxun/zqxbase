---
name: rpiv-loop:code-audit
description: >-
  对指定目录/模块/skill 进行全量代码审计（不依赖 git diff）。支持逻辑、安全、性能、架构、集成与环境、可迁移性、必要性 7 个维度的审查，特别适合审计 skills 是否绑定 Claude Code、Codex、CodeAgent 或特定机器环境。
argument-hint: "<目标> [logic|security|performance|architecture|integration|portability|necessity]"
allowed-tools: Read, Glob, Grep, Bash, Edit, Write
version: 2.17.14
---

对指定目录、文件、模块或 skill 进行全量代码审计。

## 参数解析

从 `$ARGUMENTS` 中解析：

- **第一个参数**（必填）：目标，可以是目录路径、单个文件路径、模块路径或已安装 skill 名称。
  - 已存在的相对/绝对路径：直接解析为目标路径。
  - 已安装 skill 名称（如 `rpiv-loop:code-audit`）：先在当前运行面的 skills 根目录中按 `<name-with-colon-replaced-by-hyphen>/` 解析；若不存在，再扫描该 skills 根目录下 `SKILL.md` 的 frontmatter `name` 精确匹配。若当前运行面没有可发现的 skills 根目录，停止审计并要求用户提供明确路径。
  - `self` / `自身`：当正在执行本 skill 且能发现当前 skill 目录时，解析为当前 skill 目录；否则要求用户提供明确路径。
  - 若目标无法解析，停止审计并给出候选路径，不要猜测到无关插件源目录。
- **第二个参数**（可选）：审查维度，支持中英文，以下等价：
  - `logic` | `逻辑` — 逻辑正确性
  - `security` | `安全` — 安全漏洞
  - `performance` | `性能` — 性能问题
  - `architecture` | `架构` — 架构与设计
  - `integration` | `集成` — 集成与环境兼容性
  - `portability` | `migration` | `可迁移性` | `迁移` | `环境中立` — skills/代码的跨运行面、跨工具、跨机器迁移能力
  - `necessity` | `必要性` | `价值` — 内容必要性与过度设计（该做不该做，区别于其余维度的做得对不对）
  - 逗号分隔组合：`logic,security` 或 `逻辑,安全`（中英文可混用）
  - 不提供时默认全量审查（7 个维度全部执行）
  - 当目标是 skill 目录或 `SKILL.md` 时，可迁移性维度必须执行；如果用户指定的维度不包含 `portability`，自动追加并在报告中说明原因。
  - 无论目标是什么类型、用户是否指定维度，`necessity` 维度一律执行；如果用户指定的维度不包含 `necessity`，自动追加并在报告中说明原因。自动追加时执行基础检查项，仅当用户显式指定 `necessity` 时才进入深度模式。与 `portability` 的追加叠加时（目标是 skill 且用户只指定了其他维度），两条追加原因在报告中分别说明。

**示例：**

```
/code-audit neuromem/services/                    # 全量审查
/code-audit rpiv-loop:code-audit                  # 审计已安装 skill
/code-audit self architecture                     # 审计当前 skill 的架构
/code-audit rpiv-loop:code-audit portability      # 仅审计 skill 可迁移性
/code-audit neuromem/services/ architecture       # 仅架构深度审查
/code-audit neuromem/services/ 架构               # 同上（中文）
/code-audit backend/app/api/ logic,security       # 逻辑+安全深度审查
/code-audit backend/app/api/ 逻辑,安全            # 同上（中文）
/code-audit rpiv-loop:code-audit necessity        # 必要性深度模式（找过度设计）
```

## 执行流程

### Phase 0：上下文收集

1. 读取项目根目录的 `CLAUDE.md`、`README.md`（如果存在）。若目标位于当前运行面的全局 skills 目录，同时读取该运行面的全局规则文件和目标 `SKILL.md`。
2. 读取目标目录下的 `CLAUDE.md`（如果存在）。
3. 扫描 `docs/` 目录中的编码规范文件（如果存在）。若目标 skill 明确引用共享资源目录，只读取与本次审计相关的共享引用文件，避免把整个插件树误当目标。
4. 记录项目使用的语言、框架、编码规范。
5. **运行环境识别**：从 `CLAUDE.md` 和项目配置（pyproject.toml、package.json、Dockerfile 等）中识别目标运行环境（Windows/macOS/Linux/跨平台），标记为 `cross_platform` 如果代码需在多平台运行。
6. **Git 配置检查**：检查 `.gitattributes` 是否存在、是否配置了行尾符规则（`* text=auto` 等），记录对文件内容的潜在影响；如果目标不在 git 仓库中，记录为 `not_git_repo`，不要把 git 命令失败当成审计失败。
7. **迁移目标识别**：如果目标是 skill 或 workflow，识别其预期运行面（如 Claude Code、Codex、公司 CodeAgent、普通 shell）。未知时默认按多运行面可迁移目标审查。
8. 如果 `cross_platform = true`，在 Phase 2 的逻辑审查、集成审查和可迁移性审查中自动激活跨平台兼容性检查项。

### Phase 1：文件发现

1. 扫描目标，列出所有待审计文件。目标可以是目录，也可以是单个文件；如果目标是文件，文件清单只包含该文件。
2. 排除 `.venv/`、`node_modules/`、`__pycache__/`、`.git/`、`dist/`、`build/`、`*.pyc` 等依赖、缓存和构建产物。
3. 语言代码文件包括 `.py`、`.ts`、`.js`、`.tsx`、`.jsx`、`.sh`、`.ps1` 等；配置/规范文件包括 `.toml`、`.yaml`、`.yml`、`.json`。
4. 审计 skills 时，`SKILL.md`、相关 `.md` / `.mdx` 文件和被 `SKILL.md` 直接引用的脚本也属于主审计对象，不能因为不是传统源代码而跳过。
5. 按文件类型统计并输出文件清单，供后续并行审查员或主执行者顺序审查使用。

### Phase 2：审查执行

根据参数决定执行模式：

#### 全量模式（无第二参数）

如果当前会话明确允许启动并行审查员，启动 **7 个并行审查员**，每个审查员接收完整文件清单和项目上下文（含 Phase 0 的环境信息），各自独立完整阅读每个文件后审查。若当前会话未允许或工具不可用，主执行者必须按同样 7 个维度顺序执行审查，不能因为没有并行审查员而跳过维度。

**维度 1 — 逻辑审查（基础）：**
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

**维度 2 — 安全审查（基础）：**
- SQL 注入、命令注入
- XSS 漏洞
- 硬编码密钥、API Key、密码
- 权限检查缺失
- 用户输入未验证/未转义

**维度 3 — 性能审查（基础）：**
- N+1 查询模式
- 内存泄漏（未关闭资源、无界数据结构）
- 热路径上的阻塞操作
- 不必要的重复计算或 I/O
- 可并行但串行执行的操作

**维度 4 — 架构审查（基础）：**
- SOLID 原则违反（特别是单一职责和依赖倒置）
- 层级穿透（跨层直接访问）
- 循环依赖
- 过度耦合（God Object、超长参数列表）
- 抽象泄漏

**维度 5 — 集成与环境审查（基础）：**
- **跨平台兼容性**：文件路径分隔符、行尾符（CRLF/LF）、编码、大小写敏感性在目标平台上是否一致
- **外部数据假设**：代码对外部输入（文件内容、API 返回、环境变量）的格式假设是否在所有运行环境中成立
- **配置/列表完备性**：硬编码的排除列表、白名单、映射表是否覆盖了项目中已知的所有实体。**必须用 Glob/ls 实际扫描目标目录，对比列表中的条目和实际存在的目录/文件，报告"列表中有但目录中没有"和"目录中有但列表中没有"的差异**
- **组件间契约**：函数 A 的输出被函数 B 消费时，A 的输出格式是否与 B 的输入预期一致（关注编码、分隔符、是否含 metadata/标记行）
- **环境依赖**：代码是否依赖特定的 git 配置（autocrlf）、文件系统特性（大小写）、shell 环境（PATH）、运行时版本

**维度 6 — 可迁移性审查（skills/runtime-portability，基础）：**
- **运行面中立性**：skill 是否把核心流程绑定到 Claude Code、Codex、CodeAgent 或某个公司内部自动化运行面的专属工具名、命令名、hook 名、frontmatter 字段或交互模型。
- **单一事实源**：是否存在为不同运行面维护多套互相分叉的 instructions；迁移适配是否保持为薄层，而不是复制并改写核心流程。
- **路径与安装位置中立**：是否硬编码个人绝对路径、特定 home 目录、插件源码目录、workspace 名称或机器用户名；是否优先使用 `<skill-root>`、`<plugin-root>`、环境变量、相对路径或可发现路径。
- **工具能力抽象**：是否把 `Read/Edit/Write/Bash/Glob/Grep`、`apply_patch`、`AskUserQuestion` 等平台工具当成唯一实现；是否提供等价意图或 fallback。
- **Shell/OS 中立性**：是否默认绑定 PowerShell、Bash、Windows 路径分隔符、可执行文件后缀、换行符或大小写规则；必要绑定是否明确标注适用环境和替代方案。
- **前置依赖可发现性**：外部 CLI、脚本、共享资源和凭据是否有发现规则、缺失处理和降级路径，而不是依赖某台机器的隐式安装状态。
- **同步友好性**：frontmatter、metadata 和共享资源引用是否能在多环境同步时安全裁剪或保留；是否避免把环境专属适配写进核心 workflow 导致长期分叉。

**维度 7 — 必要性审查（necessity，基础）：**
- **需求对照**：与 PRD、`rpiv/archive/` 归档记录、守卫测试对照——该功能/章节/配置项是否有需求支撑或设计意图记录。
- **使用证据**：**必须用 Grep 在项目范围内实际扫描引用**（不是凭印象判断"看起来没用"），并查 git log 该内容的引入 commit 及其 message。零引用、永不可达的死分支、从未生效的配置为确凿证据。
- **复杂度收益比（YAGNI）**：为"将来可能"预留的推测性抽象、只有一个实现的接口、只有单一调用方的封装层、防御从不发生的异常、维护成本明显大于收益的机制。
- **重复冗余**：功能已被别的 skill/hook/工具覆盖、同一逻辑多处实现、可用现成能力替代的自造轮子。**必须能指名具体的重复对象**（文件路径、skill 名或函数名），指不出具体重复方就不算重复冗余。
- **四步前置查证义务**：判定任何内容"可疑"之前必须逐步完成——① 扫守卫测试（`tests/` 等目录编码了刻意的设计意图，非对称写法往往是有意为之）；② 查 PRD 与 `rpiv/archive/` 归档记录；③ 查 git log 的引入 commit 及 message；④ 从上下文推断用途。**跳步得出的发现禁止写入报告。**
- **证据源降级**：四步中不存在的证据源记为 `not_available`（普通代码仓库没有 `rpiv/`、没有守卫测试属正常），依赖其余证据源得出结论；**不得因证据源缺失而跳过本维度**。git 不可用时沿用 Phase 0 的 `not_git_repo`，第 ③ 步记 `not_available`。
- **确凿型与存疑型分开标记**：确凿型（零引用、死分支、能指名具体重复对象）按实际影响正常定级；存疑型（四步查证全空、无法自证价值）severity **上限 medium**，issue 中注明"存疑型"，suggestion **必须包含关闭路径**——"若存在未记录的设计意图，请补录到 PRD 或守卫测试后关闭本条"。
- **查证结果并入 detail**：necessity 的问题条目写入报告时，必须把四步查证结果（各证据源 found / none / not_available）摘要成一行并入 `detail` 字段，使下方 `evidence_check` 的记录不因通用报告模板不含该字段而丢失。
- **三级审计粒度**：① 功能点/章节级（某个 Phase、配置项、fallback、参数、异常分支、抽象层、封装）；② 文件/脚本级（整个 reference 文件、工具脚本、模板该不该存在）；③ 目标整体级（该 skill/模块本身是否该存在、是否该合并到别处）——**第 ③ 级结论写入报告的"整体存在性评估"节，不混入逐条问题列表**。
- **简化方案必须功能等价**：suggestion 要写清删哪段（章节名或行号）、合并成什么、替代写法是什么。不得以删减功能充当简化，也不得为减少行数牺牲可读性或删掉真正有组织价值的抽象。

necessity 的问题条目在通用字段之外额外记录：

```yaml
necessity_type: confirmed|suspected      # 确凿型 | 存疑型
evidence_check:
  guard_tests: found|none|not_available
  prd_archive: found|none|not_available
  git_log: found|none|not_available
  context_inference: found|none
```

上述 `necessity_type` 与 `evidence_check` 是 necessity 专属的附加记录，不取代下面的通用返回格式——necessity 的问题条目同时包含通用字段与这两个附加字段。

每个并行审查员或主执行者的单维度审查返回格式：

```yaml
issues:
  - id: CA-001
    severity: critical|high|medium|low
    confidence: 0-100
    file: "path/to/file.py"
    line: 42
    issue: "一行描述"
    detail: "为什么这是问题"
    suggestion: "如何修复（含具体代码建议）"
```

#### 单项模式（指定维度）

如果当前会话明确允许启动并行审查员，启动 **1 个审查员**，执行指定维度的**深度审查**；否则由主执行者直接执行该维度深度审查。无论指定哪个维度，`necessity` 都会作为额外的基础检查项同时执行（见参数解析中的无条件追加规则），不占用深度审查名额。深度模式在基础检查项之上，额外增加专项深度检查：

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

**portability 深度模式（基础 + 额外，审计 skills 时重点执行）：**
- + **跨运行面矩阵**：逐项列出 Claude Code、Codex、CodeAgent、普通 shell 对该 skill 的要求，标出核心流程、适配层和不可迁移部分。
- + **平台专属 token 扫描**：扫描 `Claude`、`Codex`、`CodeAgent`、`AskUserQuestion`、`Read`、`Edit`、`Write`、`Bash`、`apply_patch`、绝对路径、home 目录、plugin 源路径等，判断是必要适配还是不必要绑定。
- + **迁移降级路径审计**：对每个专属工具或外部依赖，确认是否存在等价动作描述、替代命令、缺失时停止条件或人工确认路径。
- + **同步分叉风险审计**：检查是否把同一核心 workflow 复制到多个环境目录后分别修改；如果存在，建议抽出共享说明、生成脚本或明确的 adapter 区。
- + **可迁移性修复建议**：优先给出“保留单一核心流程 + 环境适配薄层”的修改方案，而不是建议维护多个独立版本。

**necessity 深度模式（基础 + 额外，仅在用户显式指定 `necessity` 时进入；自动追加时只执行基础检查项）：**
- + **全量引用矩阵**：对目标内每个可引用实体（函数、类、配置项、章节标题、参数名）用 Grep 统计项目内引用计数，输出零引用清单。
- + **推测性抽象清单**：列出所有只有单一实现的接口、只有单一调用方的封装层，逐条给出“保留”或“内联”的结论及理由。
- + **重复对象排查**：对疑似重复的功能，**必须定位到具体的重复方**（文件路径、skill 名或函数名）才产出条目；定位不到具体重复方的“感觉像重复”不写入报告。
- + **整体存在性评估强制输出**：给出完整对比论证——该目标的核心职责是什么、项目内是否已有承担同一职责的机制、合并或废弃的收益与代价分别是什么。

组合模式（如 `logic,security`）：当前会话明确允许启动并行审查员时启动对应数量的并行审查员，每个执行对应维度的深度模式；否则由主执行者逐一执行指定维度。若目标是 skill 且组合中未包含 `portability`，自动追加 `portability`。`necessity` 的追加不设条件：无论目标类型与组合内容，一律追加并执行基础检查项，追加原因与 `portability` 分别说明。

### Phase 3：汇总与过滤

1. 收集所有维度的发现。
2. 去重：同一 file:line 被多个维度报告的，合并为最高严重度。
3. **置信度过滤**：仅保留 `confidence >= 75` 的问题进入正式报告，低于 75 的归入"低置信度附录"。
   - necessity 的"存疑型"问题不因存疑而降低 confidence——其 confidence 表示"四步查证已完整执行且全部落空"这一事实的确定度（通常 ≥75），据此正常进入正式报告；"该内容是否确实无用"的不确定性由 severity 上限 medium 与"存疑型"标记承担，不通过压低 confidence 表达。
4. **稳定 ID**：为正式报告和低置信度附录中的每个问题分配稳定 ID（如 `CA-001`），后续 deferred/todo 和 code-review-fix 都引用该 ID。
5. **爆炸半径评估**：对 `severity = critical 或 high` 的问题，使用 Grep 搜索该函数/类/方法在项目中的所有引用方，记录到 `blast_radius` 字段；若目标是 Markdown/skill 规范且没有函数符号，则搜索相关 heading、frontmatter `name` 或关键短语。
6. 按严重度排序：critical → high → medium → low。

### Phase 4：健康度评分

根据审查发现计算健康度评分：

- 每个维度独立评分 0-100：
  - 起始 100 分
  - 每个 critical 扣 20 分
  - 每个 high 扣 10 分
  - 每个 medium 扣 5 分
  - 每个 low 扣 2 分
  - 最低 0 分
- 总分 = 各维度评分的加权平均（全量模式 7 维度均等权重；单项模式为该维度加自动追加的维度；skill 目标自动追加 `portability` 时纳入平均；`necessity` 无条件追加，任何模式下均纳入平均）
- 等级：A(90-100) B(75-89) C(60-74) D(40-59) F(0-39)

## 输出格式

保存到 `rpiv/validation/code-audit-{kebab-case-target-name}.md`

- 如果 `rpiv/validation/` 目录不存在则创建。
- 默认报告目录是当前工作目录的 `rpiv/validation/`。当目标位于全局 skill 安装目录或其他全局配置目录时，不要把过程报告写回全局 skill 目录，除非用户明确要求。
- `{kebab-case-target-name}` 从目标路径、文件名或 skill 名称生成（如 `neuromem-services`、`backend-app-api`、`rpiv-loop-code-audit`）

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
| 可迁移性 | {分数} | {一句话总结} |
| 必要性 | {分数} | {一句话总结} |

**统计：**
- 扫描文件数：{N}
- 发现问题数：{N}（critical: {n}, high: {n}, medium: {n}, low: {n}）
- 过滤低置信度：{N} 个

## 整体存在性评估

**结论**：{保留 | 简化保留 | 建议合并到 X | 建议废弃}（四选一）

**理由**：{该目标的核心职责；项目内是否已有承担同一职责的机制；合并或废弃的收益与代价}

> 当结论为"建议合并到 X"或"建议废弃"时，除本节叙述外，还必须在"发现的问题"列表中产出一条对应的 necessity 问题条目（带稳定 ID 与 `status: open`），并在本节标注该 ID，使该结论能进入 `code-review-fix` 闭环。结论为"保留"或"简化保留"时本节不产出问题条目——简化点已由逐条问题承载。

## 发现的问题

### Critical

id: {ID}
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

## 整体存在性评估

**结论**：保留

**理由**：{一句话说明该目标的核心职责及其不可替代性}
```

## 重要提示

- 每个并行审查员或主执行者的每个审查维度都必须**完整阅读**目标文件，不能只读片段。
- 并行审查员是加速手段，不是正确性前提；不可用时必须由主执行者顺序执行同等审查。
- 审计 skill 时，可迁移性是重点维度；优先发现会导致 Claude Code、Codex、CodeAgent 或普通 shell 之间产生长期分叉的绑定。
- necessity 是唯一在所有模式下无条件执行的维度：未指定维度时随全量执行，指定任意其他维度时自动追加（只跑基础检查项），用户显式指定 `necessity` 时进入深度模式。追加原因需在报告中说明，与 portability 的追加原因分别陈述。
- necessity 的判定必须先完成四步前置查证；查证未完成即断言"没有价值"的发现不得写入报告。存疑型问题的 suggestion 必须给出关闭路径，使误报能转化为设计意图的补录。
- 专注真正的 bug 和风险，不是风格偏好。
- 每个问题必须有稳定 ID、具体行号和可操作的修复建议；文件级问题使用最相关的行号，确实无法定位时使用 `line: 1` 并说明原因。
- 安全问题（密钥泄露、注入）标记为 CRITICAL。
- 置信度评分标准：
  - 90-100：确定是真实问题，有明确证据
  - 75-89：高度可能是问题，上下文支持判断
  - 50-74：可能是问题，但也可能有合理理由
  - 0-49：不确定，可能是误报
  - necessity 存疑型问题：按"四步查证已完整执行且全部落空"的确定度打分，不按"该内容确实无用"的推断确定度打分
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
- 必须引用审计报告中的稳定 `id`
- 文件名格式：`rpiv/todo/fix-{kebab-case-name}.md`
