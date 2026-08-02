---
name: rpiv-loop:flow-status
description: 查看过程文件的状态
allowed-tools: Bash, Edit, AskUserQuestion
version: 2.17.6
---

> `<rpiv-loop-root>` 解析顺序：环境变量 `RPIV_LOOP_ROOT` -> `CLAUDE_PLUGIN_ROOT` -> 当前插件根目录；均不存在时停止并请用户配置 `RPIV_LOOP_ROOT` 或 `CLAUDE_PLUGIN_ROOT`。

# /rpiv-loop:flow-status

## 调用

```bash
uv run --no-project python <rpiv-loop-root>/tools/flow_status.py $ARGUMENTS
```

## 输出规则

1. **原样复述** stdout 中 `__NEED_LLM__` 行**之前**的全部内容到主响应区,保持原 markdown 表格、符号、缩进。**严禁**总结、压缩、省略、加 Insight、加解读、加下一步建议。脚本退出码非 0 时简要点出失败原因,仍不增加额外发挥。
2. 若 stdout 含 `__NEED_LLM__` 单行标记,从该行起进入"指令模式":下一行是 JSON payload,再下面的 `PROTOCOL:` 段是给你的执行指令(协议由脚本运行时下发,SKILL 不重复维护)。按 PROTOCOL 段执行,完成后重跑 `uv run --no-project python <rpiv-loop-root>/tools/flow_status.py check` 输出最终一致性结果。

## 子命令

```
留空 | all | pending | in-progress | completed | <feature> | check | fix
```

默认模式与 `all` 只展示活跃过程文件和 todo；已经归档的文件不列入状态输出。需要查看归档文件时，显式使用 `archived` 状态过滤或查询具体 `<feature>`。

## 多子项目聚合（伞目录场景）

工具默认只扫 `cwd/rpiv` 的 `.md`。在**伞/monorepo 目录**（本目录 `rpiv/` 无 md，真实状态散在各子项目）下：

- 若 `cwd/rpiv/subprojects.txt` 存在（每行一个子项目 rpiv 目录路径，`#`/空行忽略），工具**自动聚合**列出的子项目，按子项目分组展示，不再误显示全 0。
- 也可手动 `--rpiv-dir A --rpiv-dir B`（可重复）做临时聚合。
- 聚合模式下 `fix` 会拒绝执行（archive/原地改文件依赖子项目 cwd），需 `cd` 到具体子项目再 `fix`。

输出规则不变：仍**原样复述** stdout，不加解读。
