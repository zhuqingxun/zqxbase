---
name: rpiv-loop:handoff-list
description: >-
  快速列出当前项目 pending handoff；支持 --all 查看 archived 历史。不加载 handoff 创建/消费 SOP。
allowed-tools: Bash
version: 2.17.6
---

> `<rpiv-loop-root>` 解析顺序：环境变量 `RPIV_LOOP_ROOT` -> `CLAUDE_PLUGIN_ROOT` -> 当前插件根目录；均不存在时停止并请用户配置 `RPIV_LOOP_ROOT` 或 `CLAUDE_PLUGIN_ROOT`。

# Handoff List: 快速查看 handoff

## 调用

```bash
uv run --no-project python <rpiv-loop-root>/tools/list_handoffs.py $ARGUMENTS
```

参数：
- 留空：只列 `pending`
- `--all`：同时列 `archived`

## 输出规则

把脚本 stdout 全部内容原样完整复述到主响应中，保持 markdown 格式、缩进和空行。不要总结、不要省略、不要进入 `rpiv-loop:handoff` 的 create / mark-consumed 流程。
