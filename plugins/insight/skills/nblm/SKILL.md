---
name: insight:nblm
description: >-
  使用 NotebookLM 生成增强输出（精美 PPTX、播客音频、视频等）。需已有 NotebookLM notebook。
  当用户提到"生成播客"、"做视频"、"精美PPT"、"nblm"、"NotebookLM 增强"时触发。
allowed-tools: Read, Write, Bash, Glob, AskUserQuestion
version: 1.1.1
---

> **依赖声明**：本命令依赖 `notebooklm` CLI，这是基于 Google NotebookLM 非官方 API 的第三方工具（非 Google 官方产品）。API 接口可能随时变更导致功能失效。安装：`uv tool install notebooklm-mcp-cli`

# NBLM: NotebookLM 输出增强

基于已有的 NotebookLM notebook（通常由 `/insight:biubiubiu` 创建），通过头脑风暴确定增强输出方案，然后自动生成、下载并组织所有产物。

## 前置条件

执行前验证：
1. **NotebookLM 登录状态**：`notebooklm status`。未登录则提示用户先执行 `notebooklm login`
2. **已有 notebook**：从 `nblm-meta.json` 或用户提供的 ID 定位

## 可用输出类型

| 类型 | 生成命令 | 下载命令 | 定制选项 |
|------|----------|----------|----------|
| 播客 | `generate audio` | `download audio` | format: deep-dive/brief/critique/debate；length: short/default/long；language |
| 视频 | `generate video` | `download video` | format: explainer/brief/cinematic；style: classic/whiteboard/kawaii/anime/watercolor/retro-print/heritage/paper-craft |
| 电影级视频 | `generate cinematic-video` | `download cinematic-video` | Veo 3 生成，需 AI Ultra，~30-40 min |
| 精美幻灯片 | `generate slide-deck` | `download slide-deck --format pptx` | format: detailed/presenter；length: default/short |
| 信息图 | `generate infographic` | `download infographic` | — |
| 报告 | `generate report` | `download report` | 多种模板 |
| 测验 | `generate quiz` | `download quiz` | — |
| 闪卡 | `generate flashcards` | `download flashcards` | — |
| 思维导图 | `generate mind-map` | `download mind-map` | JSON 格式 |
| 数据表 | `generate data-table` | `download data-table` | CSV 格式 |

## 流程

### 步骤 1：定位 Notebook

**查找优先级**：
1. `$ARGUMENTS` 中直接指定的 notebook ID
2. 搜索当前项目 `nblm-meta.json`（路径：`research/nblm-meta.json` 或 `*/research/nblm-meta.json`）
3. `notebooklm list` 展示所有 notebook，让用户选择

验证 notebook 存在且有源：
```bash
notebooklm use {notebook_id}
notebooklm source list
```

如果 notebook 无源或源数量 < 3，提示用户先通过 `/insight:biubiubiu` 添加内容，或手动添加。

### 步骤 2：头脑风暴

使用 AskUserQuestion 分两轮确定增强方案：

**第一轮：选择输出类型**

展示可用输出类型列表，让用户选择想要生成的类型（可多选）。

建议组合：
- **研究传播套餐**：播客 + 精美幻灯片 + 信息图
- **学习套餐**：测验 + 闪卡 + 思维导图
- **全套**：播客 + 视频 + 幻灯片 + 信息图 + 报告

**第二轮：定制参数**（对每个选定的类型）

- **播客**：
  - 风格：deep-dive（深度对话）/ brief（快速概览）/ critique（批判分析）/ debate（辩论）
  - 时长：short / default / long
  - 语言：中文 / 英文 / 其他
  - 特定聚焦点？（如"聚焦第3章"、"侧重竞品分析"）

- **视频**：
  - 格式：explainer（讲解）/ brief（摘要）/ cinematic（电影级，需 AI Ultra）
  - 视觉风格：classic / whiteboard / kawaii / anime / watercolor / retro-print / heritage / paper-craft
  - 特定聚焦点？

- **幻灯片**：
  - 格式：detailed（详细）/ presenter（演讲者）
  - 长度：default / short
  - 需要演讲备注？

- **其他类型**：使用默认参数，或询问是否有特定指令

**第三轮（可选）：补充源**

询问是否需要在生成前添加更多源：
```bash
notebooklm source add "{url_or_content}" -n {notebook_id}
```

### 步骤 3：生成产物

对每个选定的输出类型，执行生成和等待：

```bash
# 生成（带自然语言指令和参数）
notebooklm generate {type} "{description}" --{options} --wait -n {notebook_id}

# 如果未用 --wait，轮询状态
notebooklm artifact poll -n {notebook_id}
```

**生成顺序建议**：
1. 先生成文本类（report、quiz、flashcards、mind-map、data-table）— 速度快
2. 再生成幻灯片（slide-deck）— 中等速度
3. 最后生成音视频（audio、video、cinematic-video）— 最慢

**并行生成**：不同类型可并行启动（各用 `--no-wait`），然后统一等待。

### 步骤 4：下载产物

所有生成完成后，统一下载到 `{project}/output/nblm/`：

```bash
# 创建输出目录
mkdir -p {output_dir}/nblm

# 下载各类型产物
notebooklm download audio {output_dir}/nblm/ -n {notebook_id}
notebooklm download video {output_dir}/nblm/ -n {notebook_id}
notebooklm download slide-deck {output_dir}/nblm/ --format pptx -n {notebook_id}
notebooklm download infographic {output_dir}/nblm/ -n {notebook_id}
notebooklm download report {output_dir}/nblm/ -n {notebook_id}
notebooklm download quiz {output_dir}/nblm/ -n {notebook_id}
notebooklm download flashcards {output_dir}/nblm/ -n {notebook_id}
notebooklm download mind-map {output_dir}/nblm/ -n {notebook_id}
notebooklm download data-table {output_dir}/nblm/ -n {notebook_id}
```

### 步骤 5：后处理

1. **幻灯片修改**（如用户有需求）：
   ```bash
   notebooklm generate revise-slide "{修改指令}" --page {N} -n {notebook_id}
   ```
   修改后重新下载。

2. **站点嵌入**（如项目有站点）：
   - 播客：可嵌入 HTML5 `<audio>` 标签
   - 视频：上传到 YouTube 或直接嵌入
   - 信息图：作为图片嵌入 Markdown
   - 幻灯片：提供下载链接

3. **产物清单输出**：

```
## NBLM 增强输出清单

| 类型 | 文件 | 大小 |
|------|------|------|
| 播客 | output/nblm/audio-overview.mp3 | XX MB |
| 幻灯片 | output/nblm/slide-deck.pptx | XX MB |
| ... | ... | ... |

Notebook ID: {id}
所有产物已保存到: {output_dir}/nblm/
```

## 快捷模式

如果 `$ARGUMENTS` 包含明确的输出类型，跳过头脑风暴直接生成：

```
/nblm audio                    → 默认参数生成播客
/nblm slides                   → 默认参数生成幻灯片
/nblm audio+slides             → 生成播客 + 幻灯片
/nblm {notebook_id} video      → 指定 notebook 生成视频
```

解析规则：
- 识别类型关键词：audio/播客、slides/幻灯片/ppt、video/视频、infographic/信息图、report/报告、quiz/测验、flashcards/闪卡、mind-map/思维导图
- `+` 分隔多个类型
- 第一个类似 ID 的字符串视为 notebook ID

## 异常处理

| 情况 | 处理 |
|------|------|
| notebook 无源 | 提示先添加源或运行 `/insight:biubiubiu` |
| 生成超时 | Audio/Video 可能耗时 5-40 分钟，使用 `artifact poll` 等待 |
| 下载失败 | 重试一次，仍失败则输出 artifact 信息供用户手动下载 |
| 登录过期 | 提示用户重新 `notebooklm login` |
| cinematic-video 需要 AI Ultra | 告知用户此功能需要 Google AI Ultra 订阅 |
| 幻灯片修改失败 | 记录修改指令，建议用户在 NotebookLM Web UI 手动修改 |

## 备注

- 全程使用中文
- NotebookLM 生成的内容质量取决于 notebook 中源的质量和数量
- 播客和视频生成耗时较长（5-40 分钟），建议使用 `--wait` 或后台轮询
- 所有产物下载到 `output/nblm/`，按类型命名
- 此技能与 `/insight:biubiubiu` 共享同一个 NotebookLM notebook
- 生成前可通过 `notebooklm source add` 补充更多源以提升输出质量
