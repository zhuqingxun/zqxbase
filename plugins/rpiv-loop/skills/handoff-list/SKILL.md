---
name: rpiv-loop:handoff-list
description: >-
  立即列出当前项目所有 pending handoff (markdown 表格), 性能极高 — 不加载 handoff SKILL 完整 SOP,
  不做任何探索/思考; 支持 --all 查看 archived 历史。当用户说"查看 handoff" / "看一下 handoff" /
  "列出 handoff" / "有哪些 pending handoff" / "list handoff" / "handoff 列表" / "show handoffs"
  时优先触发。列举意图**禁止改走 rpiv-loop:handoff skill**（那是 create / mark-consumed 用的,
  不是 list 用的）。
allowed-tools: Bash
version: 2.17.10
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
