---
name: publish
description: "将 biubiubiu 研究产出集成到站点框架中。灵活检测项目环境（MkDocs/Hugo/Docusaurus），自动完成文件复制和配置更新。不执行部署，由用户自行触发。当用户提到'发布到站点'、'站点集成'、'publish'时使用。"
argument-hint: "[研究主题名或 delivery-report 路径]"
---

# Publish: 研究成果站点集成

将 `/insight:biubiubiu` 的研究产出（Markdown 报告 + 图片资产）集成到项目的站点框架中。**不执行部署**，仅完成文件集成和构建验证。

## 执行流程

### 步骤 1：定位研究产出

**查找优先级**：
1. `$ARGUMENTS` 指定的 delivery-report 文件路径
2. 搜索 `research/delivery-report-*.md`，按修改时间取最新
3. 如果都没有，提示用户先执行 `/insight:biubiubiu`

从 delivery-report 中提取：
- 研究主题（topic）
- Markdown 报告文件路径列表
- 图片资产路径

### 步骤 2：检测站点框架

按标志文件自动检测：

| 标志文件 | 框架 | 状态 |
|----------|------|------|
| `site/mkdocs.yml` 或 `mkdocs.yml` | MkDocs Material | 已支持 |
| `hugo.toml` 或 `config.toml`（含 hugo） | Hugo | 预留（TODO） |
| `docusaurus.config.js` | Docusaurus | 预留（TODO） |
| 都没有 | 无框架 | 提示用户选择 |

**无框架时**，使用 AskUserQuestion 询问：
- 初始化 MkDocs Material 站点（推荐）
- 跳过站点集成，保持文件在 `output/` 目录

### 步骤 3：MkDocs 集成（已支持）

#### 3a. 复制文件

```bash
# 创建站点目录
mkdir -p site/docs/{topic}/assets

# 复制 Markdown 报告
cp research/{topic}/*.md site/docs/{topic}/
# 或从 output/ 复制（取决于 biubiubiu 的输出位置）

# 复制图片资产
cp -r {topic}/assets/* site/docs/{topic}/assets/ 2>/dev/null || true
```

#### 3b. 更新 mkdocs.yml 导航

读取当前 `mkdocs.yml` 的 `nav` 结构，在适当位置追加新章节：

```yaml
nav:
  - ... 现有导航 ...
  - {topic-display-name}:
    - {topic}/index.md
    - 模块1标题: {topic}/module-1.md
    - 模块2标题: {topic}/module-2.md
    ...
```

模块标题从 Markdown 文件的 `# 标题` 提取。

#### 3c. 构建验证

```bash
cd site && uv run mkdocs build --clean
```

- 零错误 → 集成成功
- 有错误 → 输出错误信息，提示用户检查

### 步骤 4：输出结果

```
## 站点集成完成

- 框架：MkDocs Material
- 文件已写入：site/docs/{topic}/
- 导航已更新：mkdocs.yml
- 构建验证：PASS

### 部署方式（请手动执行）
- Railway：`git push`（如已配置自动部署）
- GitHub Pages：`uv run mkdocs gh-deploy`
- 本地预览：`cd site && uv run mkdocs serve`
```

## Hugo 集成（预留）

检测到 Hugo 项目时提示：
> "Hugo 站点集成尚未实现。请手动将 Markdown 文件复制到 `content/{topic}/` 目录。"

## Docusaurus 集成（预留）

检测到 Docusaurus 项目时提示：
> "Docusaurus 站点集成尚未实现。请手动将 Markdown 文件复制到 `docs/{topic}/` 目录并更新 sidebars.js。"

## 异常处理

| 情况 | 处理 |
|------|------|
| delivery-report 不存在 | 提示先运行 `/insight:biubiubiu` |
| mkdocs.yml 格式解析失败 | 输出原始 nav 内容，提示用户手动添加 |
| mkdocs build 失败 | 输出错误日志，不回滚已复制的文件 |
| 同名 topic 目录已存在 | 使用 AskUserQuestion 询问：覆盖 / 跳过 / 重命名 |

## 备注

- 全程使用中文
- 此命令不执行任何部署操作，部署由用户自行触发
- 如需 NBLM 增强输出（播客、信息图等），请先执行 `/insight:nblm`，再运行 publish
