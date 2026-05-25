---
name: rpiv-loop:flow-status
description: 查看过程文件的状态
allowed-tools: Bash, Edit, AskUserQuestion
version: 2.1.10
---

# /rpiv-loop:flow-status

## 调用

```bash
uv run --no-project python D:/CODE/plugins/rpiv-loop/tools/flow_status.py $ARGUMENTS
```

## 输出规则

1. **原样复述** stdout 中 `__NEED_LLM__` 行**之前**的全部内容到主响应区,保持原 markdown 表格、符号、缩进。**严禁**总结、压缩、省略、加 Insight、加解读、加下一步建议。脚本退出码非 0 时简要点出失败原因,仍不增加额外发挥。
2. 若 stdout 含 `__NEED_LLM__` 单行标记,从该行起进入"指令模式":下一行是 JSON payload,再下面的 `PROTOCOL:` 段是给你的执行指令(协议由脚本运行时下发,SKILL 不重复维护)。按 PROTOCOL 段执行,完成后重跑 `uv run --no-project python D:/CODE/plugins/rpiv-loop/tools/flow_status.py check` 输出最终一致性结果。

## 子命令

```
留空 | all | pending | in-progress | completed | <feature> | check | fix
```
