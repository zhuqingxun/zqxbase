---
name: insight
version: 1.1.0
description: >-
  Insight 洞察研究方法论——结构化深度研究流程(需求澄清→信息源发现→深度调研→写作集成→部署交付)。
  当用户提到"研究一下"、"深度调研"、"洞察研究"、"insight"时触发。
  也适用于用户说"帮我研究一下 XXX"且研究范围足够大(需要多源调研+写作+部署)的场景。
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, AskUserQuestion, Skill, WebSearch, WebFetch
version: 1.0.0
---

# Insight 洞察研究方法论

你是一名熟悉 Insight 研究流程的 AI 助手。当用户的项目安装了此插件时，你应理解并遵循 Insight 方法论来组织深度调研和洞察报告生成。

## 流程概述

Insight 是一套结构化的深度研究流程，将调研过程分为五个阶段：

```
需求澄清 → 信息源发现 → 深度调研 → 写作集成 → 部署交付
   ↑                                              ↓
   └──────────── 提示词/经验沉淀 ────────────────┘
```

| 阶段 | 核心问题 | 输入 | 输出 |
|------|---------|------|------|
| **需求澄清** | 研究什么？给谁看？ | 对话/想法 | `research/brainstorm-summary-{topic}.md` |
| **信息源发现** | 从哪里获取权威信息？ | 需求摘要 | `research/source-registry.md` + NotebookLM notebook |
| **深度调研** | 每个模块的五层深度 | 信息源 + 素材 | `research/*.md` 调研笔记 |
| **写作集成** | 转化为可交付文档 | 调研笔记 | Markdown 报告 + 站点页面 + PPT |
| **部署交付** | 让读者能访问 | 完成的文档 | 部署 URL + 交付报告 |

## 环境要求

### 必须
- **Claude Code Pro+**：biubiubiu 需要 Agent Team 功能（brainstorm/ppt-refine 无此限制）
- **uv**：Python 包管理器，PPT 生成需要

### 可选（增强体验）
- **notebooklm CLI**：`/insight:nblm` 和 `/insight:ppt-refine` NBLM 模式需要
  - 第三方工具，基于 Google NotebookLM 非官方 API，可能随时失效
  - 安装：`uv tool install notebooklm-mcp-cli`
- **LibreOffice**：ppt-refine QA 渲染验证，无则跳过视觉验证

## 目录约定

Insight 项目使用以下目录结构：

```
{项目}/
├── output/              # 正式交付物（永久保留）
│   ├── *.pptx           # PPT 报告
│   └── assets/          # 嵌入资产（图片等）
├── research/            # 研究过程文件
│   ├── brainstorm-summary-{topic}.md  # 需求摘要
│   ├── source-registry.md             # 信息源注册表
│   ├── *.md                           # 按主题的调研笔记
│   ├── nblm-meta.json                 # NotebookLM 元数据
│   ├── nblm-prompt-assets.md          # NBLM 提示词沉淀
│   ├── delivery-report-{topic}.md     # 交付报告
│   └── archive/                       # 归档的研究文件
├── generate_ppt*.py|js  # PPT 生成脚本
├── refine_ppt.py        # PPT 精加工脚本
└── site/docs/{topic}/   # 站点文档（如适用）
```

## 过程文件规范

研究过程文件使用 frontmatter 管理生命周期：

```yaml
---
description: "{类型}: {topic}"
status: pending | in-progress | completed | archived
created_at: YYYY-MM-DDTHH:MM:SS
updated_at: YYYY-MM-DDTHH:MM:SS
archived_at: null
---
```

## 命令全景图

| 命令 | 用途 | 典型触发 |
|------|------|---------|
| `/insight:brainstorm` | 研究需求澄清 | "我想研究一下 X" |
| `/insight:biubiubiu` | 全自主研究团队执行 | "自动研究"、"深度调研" |
| `/insight:ppt-refine` | PPT 精加工 | "精加工 PPT"、"PPT 增强" |
| `/insight:nblm` | NotebookLM 增强输出 | "生成播客"、"做视频" |
| `/insight:publish` | 站点集成 | "发布到站点"、"站点集成" |

## 典型工作流

### 完整研究流程

```
1. /insight:brainstorm "全球隐私保护调研"
   → 输出 research/brainstorm-summary-privacy.md

2. /insight:biubiubiu
   → Agent 团队自动完成: 信息源发现 → 调研 → 写作 → PPT → 部署
   → 输出 output/*.pptx + site/docs/ + research/delivery-report-*.md

3. /insight:ppt-refine output/xxx.pptx
   → 视觉增强: 渐变/装饰 + NBLM 信息图嵌入

4. /insight:nblm
   → 生成播客音频、视频等增强输出
```

### 单独使用

每个命令也可独立使用，不要求完整流程。例如：
- 只用 `/insight:ppt-refine` 精加工已有 PPT
- 只用 `/insight:nblm` 从已有 notebook 生成播客

## 质量标准

### 五层深度检验

每个研究模块必须覆盖：

1. **是什么**：官方定义 + 核心概念
2. **怎么工作**：技术实现原理的深度拆解
3. **为什么这样设计**：设计哲学和 tradeoff 分析
4. **竞争力何在**：与替代方案对比论证
5. **局限性**：客观指出边界和不足

### 引用规范

- 所有事实性陈述使用脚注 `[^N]`
- 格式：`[^N]: 来源名称, URL, 获取于 YYYY-MM-DD`
- 目标溯源率：100%（每条事实可追溯到原始来源）
