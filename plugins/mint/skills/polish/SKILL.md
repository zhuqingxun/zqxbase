---
name: mint:polish
description: >-
  MINT 流水线 Stage 3: 编辑稿生成——将清洁逐字稿转化为高可读性的编辑稿，产出三种文档：书面化文稿、观点+原声对照、精华语录集。包含独立 Reviewer 阶段做七维审查：观点覆盖完整性（核心）、话题/数据漏检扫描、结构化质量、原声质量、观点准确性、脱敏安全、格式可读性。适用于需要将访谈/会议记录转化为可交付文档的场景。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
version: 2.1.6
---


# mint:polish — 编辑稿生成

> **`{MINT_REF}` 路径约定**：指 mint 插件的 `references/` 目录，`{MINT_SCRIPTS}` 为同级 `scripts/` 目录。首次引用时通过
> `Glob("**/plugins/mint/references/lessons-learned.md")` 定位，多结果时优先非 `marketplaces/` 路径（私有开发版）。

将清洁逐字稿（clean）转化为高可读性的编辑稿，产出三种文档。

## 用法

```
/mint:polish <工作目录> [--template <模板文件>] [--脱敏] [--skip-review]
```

示例：
- `/mint:polish D:\WORK\访谈记录\张三访谈`
- `/mint:polish D:\WORK\会议记录\产品评审会 --template D:\访谈提纲.md`
- `/mint:polish D:\WORK\访谈记录\张三访谈 --脱敏`
- `/mint:polish D:\WORK\访谈记录\张三访谈 --skip-review` (快速迭代时跳过 Reviewer)

参数说明：
- `<工作目录>`：包含 meta.yaml 的 MINT 工作目录
- `--template`：可选，访谈提纲/会议议程文件路径，用于 structured 输出的问题结构
- `--脱敏`：同时生成脱敏版本的编辑稿和结构化分析（精华原声不脱敏——原声的价值在于保留原始表达）
- `--skip-review`：**不推荐**。跳过独立 Reviewer 审查阶段。仅在快速迭代或确认不需要质量审查时使用

## 前置条件

1. 工作目录中存在 `meta.yaml`
2. `03_校对稿/` 目录中存在清洁逐字稿 `{name}_校对稿.md`
3. 如果 clean 稿不存在，提示用户先执行 refine 阶段
4. 如果 `03_校对稿/{name}_校对稿_脱敏.md` 存在，通过 AskUserQuestion 询问用户是否使用脱敏稿作为输入。选项："使用原版校对稿" / "使用脱敏校对稿"

## 三种产出物

### 1. 编辑文稿（polished）

**文件**: `04_编辑稿/{name}_编辑稿.md`

段落重组、全面书面化的高可读性文稿。适合直接阅读或作为报告素材。

特征：
- 按话题/逻辑线索重组段落（不再按时间线排列）
- 完全书面化，消除口语痕迹
- 保留说话人标识，但去除时间戳
- 补充必要的过渡句和段落标题

### 2. 观点原声对照（structured）

**文件**: `04_编辑稿/{name}_结构化分析.md`

按问题/话题结构组织，每个话题下提炼观点并附原始发言。

特征：
- 如果提供了 `--template`，按模板的问题结构组织
- 如果没有模板，自动从对话中提炼话题结构
- 每个话题/问题下包含：观点概括 + 关键原声引用
- 详细格式和写作规则见 `{MINT_REF}/structured-prompt.md`

### 3. 精华语录集（quotes）

**文件**: `04_编辑稿/{name}_精华原声.md`

最有价值的发言片段集结，适合引用和传播。

特征：
- 精选最有冲击力、信息量最大的发言
- 按话题分类，每条附说话人和上下文简述
- 详细选取标准见 `{MINT_REF}/quotes-prompt.md`

## 执行流程

### 第零步：解析 template

在验证环境之前，先通过 `meta_io.py` 的 `resolve-template` 子命令按三层兜底规则决定本次 polish 使用的 template：

1. **显式 `--template <id-or-path>`** 最高优先
2. **meta.yaml.interviewee_type** + `workspace.yaml.interviewee_types[].default_template_id`
3. **无模板模式**（老 workspace 或 `default_template_id == null`）

调用 CLI：

```bash
if [ -n "$TEMPLATE_OVERRIDE" ]; then
  RESOLVE_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py resolve-template "<工作目录>" --template-override "$TEMPLATE_OVERRIDE")
else
  RESOLVE_JSON=$(uv run --script {MINT_SCRIPTS}/meta_io.py resolve-template "<工作目录>")
fi
```

- `$TEMPLATE_OVERRIDE` 来自 CLI 参数 `--template`；未传则不加 flag
- resolve-template 失败（exit 非 0，stderr 含 `ERROR:`）→ 直接透传错误退出，不继续后续步骤

解析返回的 JSON（三个字段）：

| 字段 | 含义 |
|------|------|
| `template_path` | 后续步骤使用的提纲文件绝对路径（null 表示无模板模式） |
| `template_id` | 写入 meta.yaml.stages.polish.params.template_override（用于 templates-remove 引用完整性检查；null 或 "adhoc" 可能出现） |
| `source` | `explicit` / `type_default` / `none`（用于日志和 Reviewer 报告） |

分支处理：

- `source in {"explicit", "type_default"}` 且 `template_path` 非 null → 正常 7 维审查（维度 1 观点覆盖度用 `template_path`）
- `source == "none"` → **无模板模式**：
  - 第四步"观点原声对照"自动从对话中提炼话题结构（不按模板问题分组）
  - 第六步 Reviewer 跳过维度 1（观点覆盖完整性），权重 25% 按比例重分到维度 2-7
  - 第八步 meta.yaml `stages.polish.review.mode` 写入 `"no_template"`

PRD 6.3 的报错分支（缺 interviewee_type 但 workspace.yaml.types[] 非空、type.default_template_id 指向不存在的 template 等）均由 resolve-template CLI 直接 exit 2 + stderr `ERROR: ...` 返回，polish 不做二次判定。

### 第一步：验证环境

1. 读取 `meta.yaml`，确认工作目录有效
2. 确认 `03_校对稿/` 中存在输入文件
3. 第零步已完成 template 解析；若 `template_path` 非 null 则读取并验证该文件存在（失败 → 报错退出；这属于注册表与实际文件系统不一致的罕见情况）
4. 从 meta.yaml 提取项目信息（project 名称等）

### 第二步：读取输入

读取 `03_校对稿/{name}_校对稿.md` 全文。如果文件较大（>50000 字），提示用户确认是否继续（LLM 上下文可能不足）。

### 第三步：生成编辑文稿

使用 LLM 将清洁逐字稿转化为编辑文稿：

**System Prompt 要点**：
```
你是资深文字编辑。任务是将访谈/会议逐字稿转化为高可读性的书面文稿。

要求：
1. 按话题和逻辑线索重新组织段落结构，不必保持原始时间顺序
2. 将口语表达全面转化为书面语，但保留说话人独特的表达风格和关键措辞
3. 为每个段落添加准确的小标题
4. 说话人标记保留但简化（如"张总指出："）
5. 去除时间戳、语气词、重复表达
6. 补充必要的过渡句使上下文连贯
7. 不添加原文中没有的观点或信息
```

对于长文本（>20000 字），分段处理：
- 先让 LLM 通读全文，输出话题结构大纲
- 再按大纲逐段生成编辑文稿
- 最后统一检查连贯性

### 第四步：生成观点原声对照

使用 `{MINT_REF}/structured-prompt.md` 中的详细指引。

- 如果第零步解析出的 `template_path` 非 null（source = explicit / type_default）：按模板的问题结构提取
- 如果 source = none（无模板模式）：先让 LLM 从对话中自动提炼 5-10 个核心话题作为结构

对于长文本或问题较多（>4 个）的场景，按 3-4 个问题一组分批处理，每批读取完整 clean 稿。

### 第五步：生成精华语录集

使用 `{MINT_REF}/quotes-prompt.md` 中的详细指引。

从 clean 稿中精选最有价值的发言片段，按话题分类组织。

### 第六步：独立 Reviewer 审查（默认启用）

> 除非指定 `--skip-review`，此步骤默认启用。Reviewer 的价值详见「为什么要 Reviewer」章节。

Leader 启动一个独立的 general-purpose agent 作为 Reviewer，传入：
1. **Clean 稿路径**：`03_校对稿/{name}_校对稿.md`
2. **待审产出物路径列表**：本次生成的文件（编辑稿/结构化分析/脱敏稿等，精华原声建议也审但优先级低）
3. **Reviewer 指引**：`{MINT_REF}/polish-reviewer-prompt.md` 的完整内容内联或让 Reviewer 自己 Read
4. **脱敏场景标识**：是否启用脱敏自检（`--脱敏` 场景启用）
5. **受访者真实姓名**：用于脱敏扫描（仅脱敏场景）

**Reviewer 执行七维审查**（详见 `{MINT_REF}/polish-reviewer-prompt.md`）：
- **维度 1：观点覆盖完整性（权重 25%，🌟 核心）** — clean 稿中受访人明确表达的所有观点（立场/判断/建议/对比/结论/诊断/反问/量化/矛盾揭示/自我反思）是否都在 polish 产出中得到完整覆盖。Reviewer 必须先做"观点提取"（按问题分段 bullet 列出所有明确观点并编号 `P{Q}-{序号}`），再做"覆盖对照"（逐条检查 polish 中的状态：✅完全覆盖/⚠覆盖不完整/❌漏检）
- **维度 2：话题/数据/案例漏检扫描（权重 15%）** — 具体数据、案例、历史背景、专有名词等**非观点类细节**的覆盖情况（维度 1 的配套细节层）
- **维度 3：结构化质量（权重 15%）** — 复杂问题是否分层/延伸分块
- **维度 4：原声质量（权重 15%）** — 抽样验证原声发言人、冲击力、观点匹配
- **维度 5：观点准确性（权重 10%）** — 已写观点是否准确反映受访者立场（与维度 1 互补：维度 1 查漏写，维度 5 查写错）
- **维度 6：脱敏安全（权重 15%，仅脱敏场景）** — 7 类扫描模式全部 grep 执行
- **维度 7：格式与可读性（权重 5%）**

**无模板模式**（第零步 `source == "none"`）：
- 维度 1 无 template 做观点分组参照 → 跳过维度 1（观点提取与覆盖对照均不执行）
- 其 25% 权重按比例重分到维度 2-7：新权重 = 原权重 × (1 / (1 - 0.25)) = 原权重 × 4/3
  - 维度 2: 15% → 20%
  - 维度 3: 15% → 20%
  - 维度 4: 15% → 20%
  - 维度 5: 10% → 13.3%
  - 维度 6: 15% → 20%（仅脱敏场景）
  - 维度 7: 5% → 6.7%
- 强制退回触发条件相应调整：维度 1 漏检条件在无模板模式下**不适用**；维度 6 critical 和加权总分 < 85 仍生效
- Reviewer 报告开头必须注明 `模式: 无模板（workspace.yaml.types[].default_template_id 为 null 或老 workspace）`

**强制退回触发条件**（任一满足即退回）：
- 维度 1 任意 critical 观点漏检（仅非无模板模式下适用）
- 维度 6 任意脱敏扫描命中
- 加权总分 < 85 或有 critical 级问题

**Reviewer 输出**：加权总分 + 问题清单（分 critical/high/medium/low 四级）+ 可操作修正建议。

**Leader 处理 Reviewer 报告**：
- **通过**（无 critical 且总分 ≥ 85）：进入第七步输出
- **退回修正**（有 critical 或总分 < 85）：Leader 依问题清单用 Edit 工具**定点修正**（不整体重写），完成后再次调用 Reviewer 复审
  - 最多 2 轮修正后仍不通过 → Leader 部分重写问题严重的问题段后第 3 轮审查
  - 第 3 轮仍不通过 → 上报用户人工介入
- **严重不合格**（总分 < 70）：Leader 重新生成对应产出物（不只是修正），然后重新审查

**关键原则**：
- Reviewer **独立视角**：不要把 Leader 的生成过程/思路传给 Reviewer，只给最终产出物 + clean 稿
- Reviewer **不可修改文件**：Reviewer 只读，修改由 Leader 基于报告执行
- Leader 修正时**优先用 Edit 定点修改**，保留已通过的部分
- 本轮审查结果记入 meta.yaml 的 `stages.polish.review` 字段

### 第七步：版本管理与输出

1. 如果 `04_编辑稿/` 中已有同名文件，将旧版移动到 `04_编辑稿/old/{name}_{type}_v{N}.md`
2. 写入本次生成的输出文件（根据用户本次要求，可能是全部或部分）：
   - `04_编辑稿/{name}_编辑稿.md`
   - `04_编辑稿/{name}_结构化分析.md`
   - `04_编辑稿/{name}_精华原声.md`
3. 如果指定了 `--脱敏`，按「脱敏版本生成规则」生成脱敏版（精华原声不脱敏）：
   - `04_编辑稿/受访者_{NN}_编辑稿_脱敏稿.md`
   - `04_编辑稿/受访者_{NN}_结构化分析_脱敏稿.md`
   其中 `{NN}` 从 `desensitization_registry.yaml` 分配（见下方规则）

### 第八步：更新 meta.yaml

```yaml
stages:
  polish:
    status: completed        # 或 partial（仅生成了部分产出物）
    version: 1               # 或递增
    completed_at: {当前 ISO 时间}
    params:
      model: "{使用的 LLM 模型}"
      has_template: true/false      # 历史遗留字段，polish 新代码不再读，保留不删（与 template_override 同步语义）
      template_override: "{id}"     # 第零步 resolve-template 返回的 template_id（或 "adhoc"/null）；用于 /mint:templates remove 引用完整性扫描
      desensitized: false    # 是否生成了脱敏版本
      outputs:               # 本次生成的产出物列表
        - {文件名 1}
        - {文件名 2}
    review:                  # Reviewer 审查结果（七维）
      enabled: true          # --skip-review 时为 false
      mode: normal           # normal / no_template（第零步 source == none 时写 no_template）
      rounds: 1              # 审查轮次
      final_score: 92        # 最终加权总分
      passed: true           # 是否通过
      critical_issues: 0     # critical 问题数（修正后）
      high_issues: 1         # high 问题数（修正后）
      dimension_scores:      # 七维得分（无模板模式下 content_coverage 缺失或置 null）
        content_coverage: 92            # 维度 1 观点覆盖完整性
        detail_coverage: 95             # 维度 2 话题/数据漏检
        structure: 90                   # 维度 3 结构化质量
        quote_quality: 95               # 维度 4 原声质量
        viewpoint_accuracy: 96          # 维度 5 观点准确性
        desensitization: 100            # 维度 6 脱敏安全
        format: 98                      # 维度 7 格式可读性
      content_coverage:      # 维度 1 观点覆盖详情（无模板模式下省略或置 null）
        total_viewpoints: 32           # 观点提取总数
        fully_covered: 30              # 完全覆盖数
        partially_covered: 1           # 覆盖不完整数
        missed: 1                      # 完全漏检数
        critical_missed: 0             # critical 观点漏检数（必须为 0 才能通过）
      desensitization_checks:  # 脱敏扫描结果（仅脱敏场景）
        name_residue: pass
        timestamp_residue: pass
        business_attribution: pass
        first_person_identity: pass   # 第一人称身份视角
        do_business_coupling: pass    # 我+做+业务名耦合
        third_party_names: pass
        alias_consistency: pass
```

**params.template_override 语义**：
- 第零步 `source == "explicit"` → 写 resolve-template 返回的 `template_id`（若用户传 `--template <path>` 且不在注册表内，该字段为 `"adhoc"`）
- 第零步 `source == "type_default"` → 写对应 `default_template_id`
- 第零步 `source == "none"` → 字段置 null（或省略）

此字段是 `/mint:templates remove <id>` 引用扫描的唯一来源（scan_meeting_template_overrides 读取），禁止留空或写别的值。

### 第九步：报告结果

报告本次生成的文件路径和各自的字数统计，附上 Reviewer 最终评分和主要问题修正记录。

同时更新 `current`：
- `current.cursor` = `"polish"`
- `current.last_action_desc` = `"完成编辑稿"`

### 最后一步：更新元数据并输出引导块

1. **刷新 current.last_action + 计算 next_hints**：
   ```bash
   uv run --script {MINT_SCRIPTS}/meta_io.py refresh-last-action "<工作目录>"
   uv run --script {MINT_SCRIPTS}/meta_io.py compute-next-hints "<工作目录>"
   ```

2. **渲染引导块**：
   - Read `{MINT_REF}/next-hints-template.md`
   - 用 compute-next-hints 输出的 JSON 填充 `{primary_cmd}` / `{primary_reason}` / `{alternatives_block}`
   - `{alternatives_block}` 按每行 `- {cmd}: {when}` 循环展开，空数组输出单行 `- 无`
   - 原样输出填充后的模板（保留开头的 `---` 分隔线）

## 质量控制

质量控制分两层：**Leader 自检**（生成后的快速检查）+ **独立 Reviewer 审查**（第六步的正式审查）。

### Leader 自检（生成时轻量检查）

每种产出物生成后，Leader 进行快速自检：

**编辑文稿自检**
- 是否有遗漏的重要话题（对照 clean 稿的主要内容）
- 段落标题是否准确概括了内容
- 是否引入了原文没有的信息

**观点原声对照自检**
- 观点是否准确反映发言人立场
- 原声是否为发言人（非提问者）的话
- 同一原声是否被多个问题重复引用

**精华语录自检**
- 语录是否确实有冲击力和信息量
- 是否标注了正确的说话人
- 上下文简述是否帮助理解语录含义

### 为什么要 Reviewer（第六步的独立审查）

Leader 自检存在天然盲点：
1. **生成者偏见**：Leader 产出后倾向于认可自己的判断，"越看越觉得写得好"
2. **漏检盲区**：Leader 在生成时已经决定了哪些内容放哪里，自检时很难跳出这个框架发现漏掉的话题
3. **脱敏复杂性**：脱敏自检需要多种扫描模式逐一执行，Leader 容易在专注产出质量时遗漏部分扫描
4. **结构化决策**：是否分层、是否延伸分块这类决策需要"第三方视角"才能客观评估

**Reviewer 的定位**：
- 看不到 Leader 的生成思路，只看最终产出物 + clean 稿
- 用结构化 checklist（7 维 + 7 类脱敏扫描）做独立判断
- 带挑刺心态找不足，不接受模糊通过
- **维度 1"观点覆盖完整性"强制使用"观点提取 → 逐条对照"方法**，而不是印象检查，避免 Leader 在生成时形成的框架盲点

**经验数据**（基于 11_迟冉 双路对抗实验，2026-04-09）：
- 独立 Reviewer 在结构化分析稿上平均能发现 2-4 处 Leader 自检忽略的问题
- 脱敏场景下，独立扫描模式库比 Leader 顺手 grep 的命中覆盖率高 ~30%
- 对比纯双路 Worker 对抗（2.3x 成本），单路 + 独立 Reviewer 成本约 1.4-1.6x，质量收益达到双路对抗的 60-70%

详见 `{MINT_REF}/polish-reviewer-prompt.md`。

## 脱敏版本生成规则

当指定 `--脱敏` 时，在正式版三个产出物完成后，额外生成编辑稿和结构化分析的脱敏版本。精华原声不脱敏（原声价值在于保留原始表达和人物特征）。

### 代号分配

脱敏稿使用匿名代号 `受访者_{NN}` 替代真实姓名。代号从访谈根目录的 `desensitization_registry.yaml` 集中分配：

```yaml
# desensitization_registry.yaml
next_id: 5
registry:
  受访者_01:
    name: 李玉蕾
    project: 01_李玉蕾
    registered_at: 2026-03-24
  # ...
```

**流程**：
1. 读取 `desensitization_registry.yaml`（路径：工作目录的**父目录**，即访谈记录根目录）
2. 如果当前受访者已注册 → 复用已有代号
3. 如果未注册 → 使用 `next_id` 分配新代号，追加到 registry，`next_id` +1
4. 如果 registry 文件不存在 → 创建文件，从 `01` 开始分配

### 编辑稿脱敏规则

输入：`{name}_编辑稿.md` → 输出：`受访者_{NN}_编辑稿_脱敏稿.md`

| 脱敏项 | 规则 | 示例 |
|--------|------|------|
| 标题 | 替换为通用标题 | `# {项目名}——编辑稿（脱敏稿）` |
| 头信息 | 删除受访者身份行和分析模式行 | 删除 `> 受访者：{姓名}（...）` |
| 受访者姓名 | 全文替换为"受访者" | "{姓名}认为" → "受访者认为" |
| 第三方真实人名 | 替换为职务/角色描述或删除 | "{人名A}" → "前一批领导"；"{人名B}" → "对口人员" |
| 可识别的组织细节 | 如受访者所在具体部门/层级可唯一定位其身份，泛化处理 | "我们地区部" → "所在组织" |
| 其他内容 | 保留原文结构和措辞 | — |

### 结构化分析脱敏规则

输入：`{name}_结构化分析.md` → 输出：`受访者_{NN}_结构化分析_脱敏稿.md`

在编辑稿的脱敏规则基础上，额外执行：

| 脱敏项 | 规则 | 示例 |
|--------|------|------|
| 标题 | `# {项目名}——结构化分析（脱敏稿）` | — |
| 问题标题 | 删除"——"后的详细补充说明 | `【问题 1：公司战略目标的承接——"看不到未来的领袖"根因...】` → `【问题 1：公司战略目标的承接】` |
| 核心问题行 | 在每个问题标题下方添加 `**核心问题：** {提纲原始问题}` | 从 `--template` 提纲中提取，无模板时从标题补充中提炼 |
| 关键原声时间戳 | 删除所有 `（HH:MM:SS）` 时间标记 | `"你老觉得..."（00:01:01）` → `"你老觉得..."` |

### 脱敏自检（Leader 生成后 + Reviewer 独立验证）

脱敏稿生成后，Leader 先执行一轮快速自检，Reviewer 在第六步再独立扫描一遍（双重验证）。

**全部 PASS 才算完成**。任一项命中即退回修正。

1. **姓名残留扫描**：`grep -E "{受访者真实姓名}" {脱敏稿}` → 零匹配
   - 双字名需单字拆分扫描（如"迟冉" → 分别 grep "迟" 和 "冉"），防止"冉"单独出现在其他词中的边缘情况

2. **第三方人名扫描**：检查 clean 稿中出现的所有真实人名是否都在脱敏稿中处理

3. **时间戳残留扫描**（仅结构化分析）：
   - 半角冒号格式：`grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}' {脱敏稿}`
   - 全角括号格式：`grep -oE '（[0-9]{2}:[0-9]{2}:[0-9]{2}）' {脱敏稿}`
   - 半角括号格式：`grep -oE '\([0-9]{2}:[0-9]{2}:[0-9]{2}\)' {脱敏稿}`
   - 三种格式都需零匹配

4. **代号一致性**：文件名中的 `{NN}` 与 registry 中分配的一致；正文中无混用其他代号

5. **业务归属第三人称动词扫描**（2026-04-08 新增·李红波案例；仅扫观点段，原声段不扫）：
   ```bash
   grep -E '他负责|他主导|他推动|他管理|他承担|他将.*给|他把.*交|她负责|她主导|她推动|她管理|她承担|他的团队|她的团队|他的业务|她的业务|他的部门|她的部门' {脱敏稿}
   ```
   命中后改为被动语态或去掉限定词。**原因**：受访者+具体业务名组合可以直接反推身份。

6. **第一人称身份视角扫描**（2026-04-09 新增·迟冉案例；仅扫观点段）：
   ```bash
   grep -E '我负责|我主导|我之前做|我现在做|我一直做|原来我|我来.*部|我所在.*部|我们部门|我们这个部门|我的部门|我所在' {脱敏稿}
   ```
   典型反例：「我之前做干部任期制，又做管理者任职资格」→ 改为「以干部任期制、管理者任职资格这类政策变革为例」。**原因**：第一人称+业务名比第三人称更直接地指向受访者身份，Leader 自检时往往只扫第三人称动词而漏掉第一人称视角。

7. **"我 + 做 + 业务名"耦合扫描**（2026-04-09 新增；仅扫观点段）：
   ```bash
   grep -E '我[之前现在一直]*做[^，。,.]*(任职资格|任期制|学发|选拔任用|调配|梯队|干部专业化|MFP|COE|HRBP|BP|招聘|薪酬|绩效)' {脱敏稿}
   ```
   业务名可根据实际访谈领域扩展。**原因**：具体业务名是身份反推的最强信号，registry 中每个受访者的负责业务字段都不同。

**关于观点段 vs 原声段的区分**：
- 业务归属动词（第 5 条）、第一人称视角（第 6 条）、我+做+业务名（第 7 条）三项**只扫观点段**
- 原声段（直接引用 clean 稿原文）保持原话，原声保真优先于脱敏
- 但原声选取时应**主动避开**会暴露身份的句子（如"我之前做 X"），Leader 在选原声时应优先挑其他有代表性的句子

**详细脱敏规则和更多扫描示例见** `{MINT_REF}/lessons-learned.md` 第三章"脱敏规则"。

## 异常处理

| 情况 | 处理 |
|------|------|
| clean 稿不存在 | 提示先执行 refine 阶段 |
| clean 稿内容为空 | 报错退出 |
| 模板文件不存在 | 报错提示检查路径 |
| 文本超长（>50000 字） | 提示用户确认，分段处理 |
| LLM 调用失败 | 报告错误，已完成的产出物保留 |
| resolve-template 报错（第零步） | 透传 stderr `ERROR: ...` 并退出。常见原因：workspace.yaml.types[] 非空但 meta.interviewee_type 缺失（老会议未升级）、type.default_template_id 指向不存在的 template、显式 `--template` 既不在注册表也不是有效路径 |
| `--template` 传入的 id 不存在于注册表 | resolve-template 会尝试当路径处理，若路径也不存在 → exit 2 + stderr |
| Reviewer agent 启动失败 | 降级为 Leader 自检（执行 `{MINT_REF}/polish-reviewer-prompt.md` 中的 7 维 checklist），在 meta.yaml 中标记 `review.enabled: true, review.mode: fallback_self_check` |
| Reviewer 第 3 轮仍退回 | 汇总全部问题清单，通过 AskUserQuestion 呈现给用户，由用户决定是否接受当前版本或人工介入 |
| Reviewer 报告脱敏 critical 失败 | **禁止**静默通过或跳过扫描。必须 Edit 定点修复命中位置后重新扫描，直到全部 PASS。若无法修复（如原文没有合适的脱敏方案），上报用户 |
| 用户明确传入 `--skip-review` | 跳过第六步，但在第八步 meta.yaml 中记录 `review.enabled: false`，并在第九步报告中显著提示"本次产出未经 Reviewer 审查" |
