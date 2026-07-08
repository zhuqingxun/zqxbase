---
name: insight:biubiubiu
description: >-
  一键启动全自主 agent 团队，自动完成从信息源发现到部署的完整研究流程。insight:brainstorm 完成后使用此命令，无需人工介入。
  当用户提到'自动研究'、'全自主研究'、'research biubiubiu'、'启动研究团队'、'深度调研'时触发。
  也适用于用户说'帮我研究一下 XXX'且研究范围足够大（需要多源调研+写作+部署）的场景。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion, WebSearch, WebFetch, Skill, SendMessage, TaskCreate, TaskUpdate, TaskGet, TaskList, TaskStop
version: 1.2.1
---

# Biubiubiu Research: 全自主研究团队执行

从对话上下文中提取研究需求，启动 agent 团队自主完成完整深度研究流程（信息源发现 → 深度调研 → 写作 → 集成 → 部署），全程无需用户介入。

## 与代码版 biubiubiu 的核心差异

| 维度 | biubiubiu（代码） | biubiubiu-research（研究） |
|------|-------------------|---------------------------|
| 核心工作 | PRD → Plan → Code → Test | Source Discovery → Research → Writing → Deploy |
| 工作量分布 | 20% 设计 + 80% 编码 | 80% 调研写作 + 20% 集成部署 |
| 质量标准 | 测试通过 + 代码审查 | 五层深度检验 + 溯源率 100% |
| 并行模式 | Dev-1/Dev-2 并行编码 | Analyst-1/2 并行写不同专题 |
| 特色集成 | — | — |
| 产出物 | 代码 + 测试 | Markdown 报告 + 站点部署 |
| 后续增强 | — | `/ppt:create` 生成演示文稿 + `/nblm` 播客/视频 |

## 团队架构

| 角色 | 职责 | 活跃阶段 |
|------|------|----------|
| **Leader**（你自己） | 协调、质量门禁、部署 | 全程 |
| **Scout** | 信息源发现（Web + YouTube）、素材提取 | 阶段 1-2 |
| **Analyst-1** | 深度调研 + 专题写作（分配的模块） | 阶段 2-4 |
| **Analyst-2**（大型项目） | 深度调研 + 专题写作（分配的模块） | 阶段 2-4 |

## 前置检查

执行前验证：

2. **项目 CLAUDE.md**：读取获取技术栈、部署目标等上下文

## 执行流程

### 步骤 1：提取研究上下文

确定研究主题（从 `$ARGUMENTS` 或对话推断，kebab-case 格式）。

**如果 `$ARGUMENTS` 是已存在的文件路径**（brainstorm-summary 或需求文档），直接使用，跳到步骤 2。

**否则**，从对话上下文和 `$ARGUMENTS` 提取研究需求，保存到 `research/brainstorm-summary-{topic}.md`：

```markdown
---
description: "研究需求摘要: {topic}"
status: pending
created_at: {YYYY-MM-DDTHH:MM:SS}
updated_at: {YYYY-MM-DDTHH:MM:SS}
archived_at: null
---

# 研究需求摘要：{topic}

## 研究愿景
- 研究主题：...
- 研究深度：概览 / 深度分析 / 专家级
- 目标读者：...
- 核心问题：要回答哪些关键问题？

## 内容模块（按优先级）
1. ...

## 产出物
- Markdown 报告：是/否

## 信息源方向
- 官方来源：...
- YouTube 频道/关键词：...
- 学术/专利：...
- 社区讨论：...

## 约束
- ...
```

### 步骤 2：项目结构初始化

判断项目结构模式：

**模式 A：insight 子项目**（当前目录有 `site/mkdocs.yml`）：
```
{topic}/
├── pyproject.toml
├── research/           # 调研笔记 + nblm-meta.json
└── output/             # Markdown 报告等产出物
site/docs/{topic}/
├── index.md               # 主线概览
├── assets/                # 架构图/截图
└── references/            # 参考资料归档
```

**模式 B：独立研究项目**（无 `site/mkdocs.yml`）：
```
research/              # 调研笔记 + nblm-meta.json
output/                # Markdown 报告等产出物
docs/                      # 研究报告输出
```

执行：创建目录结构 + `pyproject.toml`（如需要）+ `uv sync`。

### 步骤 4：团队机制说明（无需显式创建团队）

当前 Claude Code harness **没有 `TeamCreate`/`TeamDelete` 工具**。团队是**单一 implicit flat team**：你（main 会话）即 Leader，用 `Agent` 工具 spawn 的每个 named agent（Scout / Analyst）自动加入该 implicit team，可被 `SendMessage` 按 name 寻址。因此本步骤无需任何操作，直接进入步骤 5。

> 历史备注：旧 SOP 曾用 `TeamCreate` / `team_name`，当前 harness 已废弃——`Agent` 工具的 `team_name` 参数标注 "Deprecated; ignored. The session has a single implicit team."。与 `rpiv-loop:biubiubiu` 步骤 2 对齐。

### 步骤 5：创建任务结构

```
阶段 1：信息源发现（Scout + Deep Research 并行）
  T1 source-discovery     → Scout 系统搜索信息源 + YouTube 视频
  T1.5 deep-research      → Leader 通过 `Skill` 工具并行启动内置 `deep-research` skill [与 T1 并行]

阶段 2：素材获取与深度调研
  T2 material-fetch       → Scout WebFetch 关键源 + 提取图片/图表   [blockedBy: T1]

阶段 3：深度写作
  T3 write-modules        → Analyst(s) 撰写各专题模块               [blockedBy: T2]
  T4 write-overview       → Analyst 撰写主线概览 + 参考资料归档      [blockedBy: T3]

阶段 4：集成&部署
  T5 delivery-report      → Leader 生成交付报告                     [blockedBy: T4]
```

### 步骤 6：启动团队

**spawn 机制**：用 `Agent` 工具 spawn 每个角色，参数：`name` = 角色名（如 `scout` / `analyst-1`）、`subagent_type` = `general-purpose`、`run_in_background` = `true`（不阻塞 Leader 协调）。**不要传 `team_name`**（已废弃且被忽略）。spawn 出的 named agent 自动加入 implicit team，后续用 `SendMessage`（`to` = 角色名）双向通信；spawn 返回的 `agent_id` 可用于 `TaskStop` 兜底。

**第一批（并行启动 2 个 agent）：**

#### Scout Agent

名称：`scout`

提示词要点：
- 你是研究团队的信息侦察员，负责发现和获取一手权威材料
- **首要步骤**：读取项目 CLAUDE.md 和研究需求摘要 `{brainstorm-path}`
- **阶段 1：信息源发现**
  - 对每个内容模块，执行以下搜索：
    1. `WebSearch` 官方来源（官网、文档、白皮书、博客）
    2. `WebSearch` 学术/专利来源
    3. **YouTube 视频搜索（必做，每个模块至少搜一次）**：`WebSearch "{topic} {module-keyword} conference OR keynote OR talk OR demo site:youtube.com"`
    4. `WebSearch` 社区讨论（HN、Reddit、论坛）
    5. `WebSearch` 第三方分析报告
  - 按 Tier 分级（Tier 1 高价值 → Tier 5 补充参考）记录每个信息源
  - 保存信息源注册表到 `{research-dir}/source-registry.md`

- **阶段 2：素材获取**
  - `WebFetch` 关键页面，提取核心内容保存到 `{research-dir}/` 按主题命名的笔记文件
  - 提取架构图/截图：PDF 用 PyMuPDF、网页图片用 requests 下载
  - 保存图片到 `assets/` 目录，记录每张图的来源 URL 和获取日期
  - 识别信息缺口 → 执行补充搜索- 你是阶段 1-2 的角色，material-fetch 完成后等待 shutdown
- **完成任务的固定顺序**：标记 TaskUpdate completed 之前，必须先 Edit 对应的 `research/` 文件，将 frontmatter `status` 更新为 `completed`、`updated_at` 更新为当前时间戳。顺序：Edit frontmatter → TaskUpdate completed，不可颠倒
- 全程使用中文

**第二批（门禁 2 通过后启动）：**

#### Analyst Agent

名称：`analyst-1`（如有第二个则 `analyst-2`）

提示词要点：
- 你是研究团队的深度分析师，负责调研写作
- **首要步骤**：读取项目 CLAUDE.md、研究需求摘要、信息源注册表
- 你负责的模块：{Leader 根据需求摘要分配的具体模块列表}
- **写作框架（五层深度检验，每个模块必须覆盖）**：
  1. **是什么**：官方定义 + 核心概念
  2. **怎么工作**：技术实现原理的深度拆解
  3. **为什么这样设计**：设计哲学和 tradeoff 分析
  4. **竞争力何在**：与替代方案对比论证
  5. **局限性**：客观指出边界和不足
- **引用规范**：所有事实性陈述使用脚注 `[^N]`，格式：`[^N]: 来源名称, URL, 获取于 YYYY-MM-DD`
- **图片规范**：每个模块至少 1 张图片（架构图/截图），使用 `![描述](assets/filename.png)` + `*来源：...*` 标注
- **信息获取优先级**：
  1. 先检查 `{research-dir}/` 已有调研笔记
  2. 不足则自行 `WebSearch`/`WebFetch` 补充
- **完成任务的固定顺序**：Edit frontmatter → TaskUpdate completed，不可颠倒
- 全程使用中文

### 步骤 7：阶段协调

#### 门禁 1：信息源就绪

Scout 完成 source-discovery 后：
- 检查信息源注册表覆盖所有内容模块
- 检查每个模块至少有 3 个独立信息源
- **YouTube 检查**：确认每个模块都搜索过相关视频（即使无高价值结果，需记录"已搜索"）
- **Frontmatter 校验**：`grep ^status:` 检查源注册表文件
- 通过 → Scout 进入素材获取

#### 门禁 2：素材就绪

Scout 完成 material-fetch 后：
- 检查 `{research-dir}/` 包含按主题组织的调研笔记
- 检查 `assets/` 包含提取的架构图/截图
- 分配模块给 Analyst(s)：
  - 单 Analyst：全部模块按优先级顺序写
  - 双 Analyst：按模块主题拆分（确保模块间无强依赖或明确指定写作顺序）
- 通过 → 启动 Analyst agent(s)

#### 门禁 3：写作完成

所有专题模块写作完成后，Leader 执行质量审查：
- **五层深度检验**：每个模块是否覆盖"是什么→怎么工作→为什么→竞争力→局限性"
- **溯源抽查**：随机抽取 30% 的脚注引用，验证 URL 格式正确且有获取日期
- **图片检查**：每个模块至少 1 张图片且有来源标注
- **交叉链接检查**：模块间引用是否指向正确的文件路径
- 有质量问题 → SendMessage 要求 Analyst 修改（最多 2 轮）
- 通过 → 概览写作

#### 门禁 4：集成完成

- **站点构建**（如适用）：零错误
- 通过 → 交付

### 步骤 8：完成交付

**先输出以下 checklist，然后逐项执行并勾选**：

```
交付 checklist：
- [ ] 8.1 生成交付报告
- [ ] 8.2 关闭团队
- [ ] 8.3 归档过程文件
- [ ] 8.4 向用户报告
```

1. **生成交付报告**保存到 `research/delivery-report-{topic}.md`：

```markdown
---
description: "交付报告: {topic}"
status: completed
created_at: {timestamp}
updated_at: {timestamp}
archived_at: null
related_files:
  - research/brainstorm-summary-{topic}.md
---

# 交付报告：{topic}

## 完成摘要
- 研究主题：{topic}
- 内容模块数量：{N} 个专题 + 1 个概览
- 信息源数量：{N} 个（Tier 1-5 分布）
- 图片数量：{N} 张架构图/截图

## 产出物清单
- Markdown 报告：{文件路径列表}

## 后续可选步骤
- `/ppt:create` — 基于研究报告生成演示文稿
- `/insight:nblm` — 生成播客、视频等增强输出

## 关键发现摘要
{3-5 条最重要的研究发现}

## 信息缺口与局限
{已标注的信息不足之处}

## 建议后续步骤
{推荐的深化方向}
```

2. **关闭团队**：对每个仍活跃的 named teammate 用 `SendMessage` 发送 `{"type": "shutdown_request", "reason": "..."}`，agent 回 `shutdown_response approve=true` 后自行终止。**当前 harness 无 `TeamDelete`**，无需也不能调用。某 agent 无响应时用 `TaskStop`（task_id = spawn 返回的 agent_id）强制终止兜底
3. **归档过程文件**：将 `research/` 下的过程文件归档到 `research/archive/`（与 biubiubiu 相同流程）
4. **向用户报告**：输出产物清单，提示可用 `/ppt:create` 生成演示文稿 + `/insight:nblm` 增强输出
## 上下文控制契约（防主 context 爆仓）

本 skill 的编排核心是**让重 IO 在子 agent 独立 context 里发生，主 agent（Leader）只持有编排状态**。各角色遵守以下契约，使全流程主 context 峰值可控、可长时间稳定运行。

### 子 agent → Leader 的回传纪律（tool-result clearing）

Scout / Analyst 做 `WebFetch`、大文件读取、深度研究输出提取等**重 tool result** 操作后：

- **原始内容一律落盘**到 `research/` 对应笔记/模块文件，**不**通过 SendMessage 把全文回传给 Leader
- 回 Leader 的 `SendMessage` 只含「**产物路径 + 体积（行数/字数）+ ≤3 条核心要点**」
- 反例（禁止）：把抓取的网页全文、专题模块全文粘进 SendMessage 给 Leader

### Leader 的 context 边界

- 门禁审查（门禁 1/2/3）对子 agent 产物**就地 Read + 出结论**，只保留审查结论（通过 / 问题清单），**不把被审产物全文搬运进后续编排消息**
- 大体量调研产出（deep-research 报告 `research/deep-research-{topic}.md` 等）**先落盘**，Leader 读后只提炼关键结论入编排，不在主 context 长期保留全文
- Scout 是阶段 1-2 临时角色，`material-fetch` 完成即 shutdown 释放其 context

### 各阶段 tool result 体积预算（软约束，超出即落盘 + clearing）

| 阶段 | 主要 tool result | 预算 / 处理 |
|------|-----------------|------------|
| 信息源发现 | WebSearch 结果 | 子 agent 内消化，回传仅注册表路径 |
| 深度调研 | 深度研究 / WebFetch 输出，单次常 5-10k tokens | 落盘，回传 ≤3 要点（tool-result clearing） |
| 专题写作 | 6 模块全文，12-30k tokens | 落盘 `research/` 模块文件，主 context 不持有全文 |
| 部署验证 | 构建日志 | 子 agent / Leader 内消化，仅留结论 |

> 进阶手段（当前不做，按需启用）：checkpoint + 多 session 续跑（阶段数 ≥5 且需中断时）、分层 `/compact`（主 context 仍逼近压缩线时手动触发，`focus` 保留站点结构决策 + 未完成模块清单）。当前以「子 agent 隔离 + 落盘 + clearing」为主，已覆盖绝大多数场景。

## 规模自适应

根据内容模块数量调整团队配置：

| 规模 | 判断标准 | 团队配置 |
|------|----------|----------|
| 小型 | ≤3 个内容模块 | Leader + Scout(兼 Analyst) — 2 agent |
| 中型 | 4-7 个模块 | Leader + Scout + Analyst — 3 agent |
| 大型 | 8+ 个模块 | Leader + Scout + Analyst-1 + Analyst-2 — 4 agent |

在步骤 1 完成后，根据内容模块数量选择配置。

## 异常处理

| 情况 | 处理 |
|------|------|
| YouTube 搜索无结果 | 记录"已搜索 {关键词} 无高价值视频"，不阻塞，继续 Web 调研 |
| YouTube WebFetch 超时 | **不要 WebFetch YouTube 页面**（JS 渲染导致超时）。只用 WebSearch 获取视频标题/描述/URL，提取关键信息到调研笔记 || 信息源不足（模块 < 3 源） | 扩大搜索范围，降低 Tier 标准，在报告中标注信息缺口 |
| 写作深度不够 | SendMessage 具体指出缺失的层次，要求 Analyst 补充（最多 2 轮） |
| **Agent 卡死（15 分钟无输出）** | **硬性超时**：检查 output 文件行数和最后时间戳。15 分钟无新输出 → 放弃该 agent，Leader 用已有数据快速补充缺口。不要无限等待 |
| Agent 部分完成后卡死 | 读取该 agent 的 output 文件，提取已完成的部分结果（可能含有价值），然后 Leader 补充剩余 |

## 备注

- 全程使用中文进行文档和沟通
- 所有产出文件遵循 insight 的 frontmatter 规范（status/created_at/updated_at/archived_at）
- agent 之间关键指令单独发送短消息，不要混在长文本中
- Scout 是阶段 1-2 角色，素材获取完成后关闭以节省资源
- 如果项目已有调研笔记或部分内容，可跳过对应阶段，从现有文件继续
- **所有研究成果必须发布到站点**：deep-research 报告等调研产出物，不能仅保存在 `research/` 目录。必须在站点集成阶段将其作为独立页面或模块子页面发布到 `site/docs/` 并添加到 mkdocs.yml 导航。发布形式（独立深度专题 / 打散融入现有模块 / 附录）由 Leader 根据内容与现有结构的关系自主判断