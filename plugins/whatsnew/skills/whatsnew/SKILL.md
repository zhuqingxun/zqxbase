---
name: whatsnew
description: 列出 Claude Code 指定版本的更新内容。当用户询问 Claude Code 更新了什么、新版本功能、changelog、release notes、最新版本变化时使用
argument-hint: [版本号，如 2.1.59、59-61、2.1.59-61，留空则查最新版本]
allowed-tools: Bash, WebSearch, WebFetch
---

## 任务

列出 Claude Code 指定版本的更新内容（changelog / release notes）。

## 版本号解析

用户输入的版本号参数为：`$ARGUMENTS`

解析规则（按优先级）：
1. **空参数**：查询最新版本的更新内容
2. **完整版本号**（如 `2.1.59`）：查询该单一版本
3. **完整版本范围**（如 `2.1.59-61`）：查询 2.1.59 到 2.1.61 的所有版本
4. **短版本号**（如 `59`）：自动补全为 `2.x.59`（x 根据搜索结果判断）
5. **短版本范围**（如 `59-61`）：自动补全为 `2.x.59` 到 `2.x.61`

## 信息获取

**优先使用 `gh` CLI**（速度快 5 倍），仅在 gh 不可用时 fallback 到 WebSearch + WebFetch。

### 方式一：gh CLI（优先）

1. 用 `gh release list --repo anthropics/claude-code --limit N` 获取版本列表和 tag
2. 用 `gh release view <tag> --repo anthropics/claude-code` 获取每个版本的详细 release notes
3. 多个版本可并行调用 `gh release view`

### 方式二：WebSearch + WebFetch（fallback）

仅当 `gh` 命令不可用（未安装或未认证）时使用：

1. 用 WebSearch 搜索 `Claude Code changelog release notes {版本号}`
2. 用 WebFetch 读取 GitHub Releases 页面，提取目标版本的更新内容

## 输出格式

用中文总结，保持简洁。格式如下：

```
## Claude Code vX.Y.Z 更新内容

**发布日期**：YYYY-MM-DD

### 新功能
- ...

### 改进
- ...

### 修复
- ...
```

如果是版本范围，按版本号从新到旧依次列出。技术术语保留英文原文。
