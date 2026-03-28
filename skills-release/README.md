# 独立 Skills (ZIP)

预打包的技能包，解压即用，无需 marketplace。

## 安装方法

1. 下载所需的 `.zip` 文件
2. 解压到 `~/.claude/skills/`（全局）或 `<项目>/.claude/skills/`（项目级）
3. 重启 Claude Code 会话

## 可用技能

| 文件 | 说明 | 技能数 |
|------|------|--------|
| `rpiv-loop-skills.zip` | RPIV 结构化开发流程 | 20 个（brainstorm, create-prd, plan-feature, execute, validation 等） |
| `mint-skills.zip` | MINT 会议智能处理管线 | 9 个（transcribe, refine, polish, extract, patch 等） |
| `insight-skills.zip` | Insight 深度研究方法论 | 6 个（brainstorm, biubiubiu, nblm, ppt-refine, publish） |
| `challenge-skills.zip` | 红蓝对抗结构化审查 | 1 个 |
| `reflect-skills.zip` | 会话复盘与经验提取 | 1 个 |
| `whatsnew-skills.zip` | Claude Code 版本更新查看 | 1 个 |

## 也可通过 Marketplace 安装

```
/plugin marketplace add zhuqingxun/zqxbase
```

ZIP 版本与 marketplace 插件版本始终保持同步。
