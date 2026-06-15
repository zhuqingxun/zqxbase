---
description: "立即列出当前项目所有 pending handoff (markdown 表格), 性能极高 — 不加载 handoff SKILL 完整 SOP, 不做任何探索/思考。当用户首条消息含'查看 handoff' / '看一下 handoff' / '列出 handoff' / '有哪些 pending handoff' / 'list handoff' / 'handoff 列表' / 'show handoffs' 时优先触发此 command。**禁止改走 rpiv-loop:handoff skill** (那是 create / mark-consumed 用的, 不是 list 用的)."
argument-hint: "留空=列 pending | --all=连 archived 一起列"
allowed-tools: Bash
---

参数: `$ARGUMENTS`

请用 Bash 工具执行:

```bash
uv run --no-project python "${CLAUDE_PLUGIN_ROOT}/tools/list_handoffs.py" $ARGUMENTS
```

把脚本 stdout 全部内容**原样完整复述到你的主响应中**(保持原 markdown 格式、缩进、空行、emoji、表格), 逐字粘贴, 不要总结、不要省略、不要加注释、不要走 handoff SKILL.md 的任何步骤。复述完成后不需任何额外说明。
