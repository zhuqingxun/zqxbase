# skill 产物的计划阶段指引

## 适用条件与本文件的三项职责

由 plan-feature 阶段 0 在 PRD frontmatter `product_types` 含 `skill` 时分派进入。plan-feature 把三件事委托给本文件，下面三节一一对应，**缺一件计划即不完整**：

| 委托事项 | 对应本文件 | 作用于 plan-feature 的哪一步 |
|---------|-----------|---------------------------|
| 调研内容替换 | 第一节 | 阶段 2「代码库情报收集」 |
| 结构设计决策 | 第二节 | 计划正文的「解决方案陈述 / 要遵循的模式」 |
| 标准 AC 注入 | 第三节 | 阶段 5.6 的 acceptance.yaml 产出 |

纯 skill 产物用本文件替换对应内容；混合产物（`[code, skill]`）两套都做，见第四节。

## 一、阶段 2 替换：同插件 skill 惯例调研

纯 skill 产物没有函数调用链、没有数据流，把「代码库情报收集」原样套用会产出空洞的调研结论。改为调研**目标插件的既有惯例**——新 skill 必须长得像它的邻居。

### 调研清单

| 维度 | 调研什么 | 怎么查 |
|------|---------|--------|
| 命名约定 | skill 目录名与 frontmatter `name` 的形态、是否带插件名前缀 | 列目录 + 读若干个同插件 SKILL.md 的 frontmatter |
| 目录结构 | `skills/` `references/` `tools/` 三者的既有分工边界 | 列插件根目录，看哪类内容落在哪 |
| 版本约定 | 插件 `plugin.json` 的 version 与各 SKILL.md 的 version 是否联动 | 对比历史提交中两者的变更是否同步 |
| frontmatter 字段惯例 | `allowed-tools` / `argument-hint` 的既有用法与粒度 | 抽 3-5 个同插件 SKILL.md 横向对比 |
| references 组织方式 | 一层深约束、文件命名风格、正文如何引用 | 看既有 references 文件与引用它的正文行 |
| 资源定位约定 | 插件内资源用什么占位符表达（如 `<plugin-root>` 类写法） | 搜正文中出现的占位符与其解析顺序声明 |

### 产出格式

调研结论写进计划的「要遵循的模式」一节，逐条给出**结论 + 出处**（哪个文件的哪一段），不写「大致如此」。新 skill 若要偏离某条既有惯例，必须在该条下写明偏离理由。

## 二、结构设计决策（计划必含，缺失视为计划不完整）

### progressive disclosure 三层判定

| 内容特征 | 归属层 |
|---------|--------|
| 触发判定、分支分派、每次执行都必须遵守的约束 | SKILL.md 正文 |
| 只在某个分支才需要的细节、可复制模板、验收清单 | references |
| 确定性强、容易写错、需重复执行的操作 | scripts |

判定口诀：**正文回答「要不要做、走哪条路」，references 回答「这条路怎么走」，scripts 承担「不该让模型每次现写的机械动作」。**

### 自由度选档

| 任务性质 | 给什么 | 自由度 |
|---------|--------|--------|
| 脆弱 / 确定性操作（格式转换、校验、批量改写） | 给脚本，模型只负责调用与读结果 | 低 |
| 启发式 / judgment 任务（写作、评审、方案权衡） | 给方向、判据与反模式，不给逐步指令 | 高 |

**选错的两种症状**：给低自由度任务留了高自由度 → 每次执行结果不一致、边界情况反复出错；给高自由度任务写死步骤 → 产出千篇一律、遇到计划外输入就卡住或硬套模板。

### 是否捆绑 scripts 的判定规则

同时满足以下三条才捆绑，否则不写脚本（多写一个脚本就多一份维护面与跨平台风险）：

1. 操作是确定性的，输入相同则输出必然相同
2. 让模型每次现写容易出错，或代价明显高于调用现成脚本
3. 在本 skill 的主路径上会被反复执行，不是一次性动作

### reference 拆分策略

- **何时拆**：正文接近 500 行 / 出现互斥分支（走 A 就不看 B）/ 某段内容只服务少数场景
- **拆几个**：**按分支拆，不按篇幅切**。一个分支一个文件，读者一次只需要读一个；把一篇长文腰斩成上下两半是反模式
- **一层深硬约束**：`references/` 下只允许一级子目录，不出现二级嵌套。层级越深，模型越难判断该读哪个

### 产出示例

> SKILL.md 正文 180 行 + references 2 个文件（X 用于 A 分支 / Y 用于 B 分支）+ 无 scripts。理由：A、B 两条分支互斥且各自细节超过 100 行，放正文会让每次执行都读到无关内容；本 skill 无确定性重复操作，捆绑脚本不满足判定规则第 3 条。

## 三、阶段 5.6 的 skill 标准 AC 注入清单

在 acceptance.yaml 中注入以下 7 条标准 AC（按特性实际情况裁剪，删除的条目要在计划中说明理由）：

```yaml
criteria:
  - id: AC-SKILL-FRONTMATTER
    given: 交付的 SKILL.md
    when: 读取其 YAML frontmatter
    then: name 为小写连字符且 <= 64 字符，description 非空且 <= 1024 字符
    verification_method: "Read SKILL.md 前 10 行，逐字段比对；description 字符数用 wc -m 统计"
    blocking: true
  - id: AC-SKILL-DESCRIPTION
    given: 交付的 SKILL.md description
    when: 逐句归类其内容
    then: 仅含「做什么 + 何时用」，不含任何工作流步骤描述
    verification_method: "逐句判定，出现祈使步骤或阶段划分即判失败"
    blocking: true
  - id: AC-SKILL-SIZE
    given: 交付的 SKILL.md
    when: 统计正文行数
    then: 行数 < 500；已超限的存量文件区分 preexisting 并另立 todo
    verification_method: "wc -l SKILL.md"
    blocking: true
  - id: AC-SKILL-DISCLOSURE
    given: 交付的 skill 目录
    when: 检查 references 目录深度与正文内容分层
    then: 无二级子目录；正文不含只服务单一分支的大段细节
    verification_method: "find references -mindepth 2 -type d 无输出；正文抽查分派行是否只做分派"
    blocking: true
  - id: AC-SKILL-PATH-NEUTRAL
    given: 本次新增或改动的 skill 文件
    when: 跑绝对路径正则扫描
    then: 零命中
    verification_method: "对目标文件跑绝对路径扫描（命令见 skill-validation-checklist.md 的 G5）"
    blocking: true
  - id: AC-SKILL-TRIGGER
    given: PRD 的 should / should-not-trigger 清单
    when: 各抽若干条做触发抽测
    then: 命中情况已记录；未命中条目记入 notes
    verification_method: "新会话中按抽测条目实测，记录命中/未命中/误触发"
    blocking: false
  - id: AC-SKILL-BASELINE
    given: 客观可验证类 skill
    when: 与 baseline（新建 = 无 skill 裸跑 / 优化 = 旧版本）对照
    then: >= 3 个真实场景有差异记录，原始输出已留档
    verification_method: "按 skill-eval-guide.md 的操作流程执行，evidence 指向留档路径"
    blocking: false
```

### verification_method 怎么填才过得了 check_acceptance.py

该校验只要求 `verification_method` **非空**，不执行其内容——所以它挡不住「填了等于没填」。硬要求：

- **人工步骤写成可复现的动作序列**：写清读哪个文件、看哪一段、按什么判据下结论
- **禁止**填 `manual` / `人工检查` / `见计划` 这类无信息量文本
- 命令型给出可直接粘贴执行的完整命令，不写「跑一下相关测试」

## 四、混合产物（code + skill）的计划要点

- **两套 gate 取并集**：skill 侧质量门与代码侧 lint / test / coverage 都要有，脚本部分照常写 pytest 任务
- **AC 分组呈现**：skill 类 AC 与代码类 AC 分两组列出，避免 skill 条目在数量上遮蔽代码条目、导致验收时代码侧被跳过
- **阶段划分不混编**：计划的实施阶段里，纯新增文档类任务与改动代码类任务分开成组，前者无回归风险可并行，后者需按依赖串行

## 自检清单

- [ ] 阶段 2 的调研六个维度逐条有结论，且每条给出出处
- [ ] progressive disclosure 三层归属已明确写出，不是「视情况而定」
- [ ] 自由度选档已给出，并说明为什么是这一档
- [ ] 是否捆绑 scripts 有明确结论，不捆绑时说明未满足哪一条判定规则
- [ ] references 拆分方案按分支拆，且满足一层深
- [ ] 7 条标准 AC 已注入 acceptance.yaml，裁剪的条目有理由
- [ ] 每条 AC 的 verification_method 都是可复现动作，非空话
- [ ] 混合产物时，代码侧 AC 与 skill 侧 AC 分组且都不为空
