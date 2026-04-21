# zqxbase

Claude Code 插件市场 — 结构化开发流程、会议智能处理、深度研究、效率工具集。

Claude Code plugin marketplace — structured workflows, meeting intelligence, deep research, and productivity tools.

## 安装 / Install

### 方式一：Marketplace（推荐）

```bash
# 添加市场 / Add the marketplace
/plugin marketplace add zhuqingxun/zqxbase

# 按需安装 / Install plugins (pick what you need)
/plugin install rpiv-loop@zqxbase
/plugin install mint@zqxbase
/plugin install insight@zqxbase
/plugin install challenge@zqxbase
/plugin install reflect@zqxbase
/plugin install whatsnew@zqxbase
```

### 方式二：独立 ZIP

从 [`skills-release/`](./skills-release/) 目录下载 zip 文件，解压到 `~/.claude/skills/` 即可使用，无需 marketplace。

## 插件 / Plugins

### rpiv-loop
结构化开发流程：**需求 → 计划 → 实施 → 验证**。

Structured development workflow: **Requirements → Plan → Implementation → Validation**.

提供完整的功能开发生命周期管理：头脑风暴、PRD 创建、计划制定、实施执行、多维度验证（代码审查、审计、交付报告）。

**主要命令**: `/rpiv-loop:brainstorm`, `/rpiv-loop:plan-feature`, `/rpiv-loop:execute`, `/rpiv-loop:code-review`

### mint
**MINT (Meeting Intelligence)** — 从录音到结构化洞察的全流程管线。

Audio-to-insights pipeline for meeting recordings.

通过 4 个阶段将会议录音转化为结构化输出：
1. **Transcribe** — ASR 语音识别 + 说话人分离
2. **Refine** — 双路交叉校对清洁
3. **Polish** — 编辑稿、结构化分析、精华语录
4. **Extract** — 要点摘要、发言人分析、行动项、决策记录

> **依赖说明**: Stage 1 (Transcribe) 依赖阿里云百炼 ASR API (`dashscope`)，需要阿里云账号和 API Key。Stage 2-4 无外部依赖，可配合任何 ASR 转录稿使用。所有 prompt 面向中文会议场景。
>
> **Dependency note**: Stage 1 requires Alibaba Cloud Bailian ASR API (`dashscope`). Stages 2-4 work with any transcript and have no external dependencies. Prompts are designed for Chinese-language meetings.

**主要命令**: `/mint`, `/mint:transcribe`, `/mint:refine`, `/mint:polish`, `/mint:extract`

### insight
**Insight** — 结构化深度研究流程。

Deep research methodology: brainstorm → source discovery → deep research → writing → delivery.

**主要命令**: `/insight:brainstorm`, `/insight:biubiubiu`, `/insight:nblm`

### challenge
红蓝对抗 — 结构化攻防审查方案和决策。

Red-Blue adversarial review: structured attack-defense analysis on plans, architectures, and decisions.

### reflect
会话复盘 — 提取可沉淀的经验教训，区分知识类与行为类经验，精准写入规则。

Session retrospective — extract reusable lessons with knowledge vs. behavior classification.

### whatsnew
版本更新查看器 — 查询 Claude Code release notes。

Claude Code changelog viewer: check what's new in any release.

## License

MIT
