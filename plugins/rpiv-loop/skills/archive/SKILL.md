---
name: rpiv-loop:archive
description: 归档已完成的过程文件
allowed-tools: Bash, Read, AskUserQuestion
version: 2.17.4
---

> `<rpiv-loop-root>` 解析顺序：环境变量 `RPIV_LOOP_ROOT` -> `CLAUDE_PLUGIN_ROOT` -> 当前插件根目录；均不存在时停止并请用户配置 `RPIV_LOOP_ROOT` 或 `CLAUDE_PLUGIN_ROOT`。

# Archive: 归档 RPIV 过程文件

正常情况下走纯 Python 脚本,**不调 LLM 推理**。归档全程机械:扫描候选 → 检查 status → 改 frontmatter → mv 文件 → 重名加时间戳 → 输出报告。

## 调用脚本

```bash
uv run --no-project python <rpiv-loop-root>/tools/archive.py $ARGUMENTS
```

## 用法

```
/rpiv-loop:archive all                          # 归档所有 completed/superseded
/rpiv-loop:archive <feature-name>               # 归档 *-<feature>.md 中符合条件者
/rpiv-loop:archive rpiv/<sub>/<file>.md         # 归档单文件
/rpiv-loop:archive <target> --dry-run           # 不动文件,仅列计划
/rpiv-loop:archive <target> --force             # 允许归档 in-progress 文件(谨慎)
```

⚠️ **feature 模式建议先 `--dry-run`**:特性名按 `*-<feature>.md` 后缀匹配,短名(如 `defects`)可能误匹配多个文件(如 `prd-ppt-skill-c-level-defects.md`)。**用户输入 feature 名时优先建议加 `--dry-run` 跑一遍**,确认候选列表无歧义后再实际归档。

## 输出处理规则

- 把脚本 stdout **原样复述**到主响应区(保留归档报告的全部 markdown 结构、条目细节、总计行)。
- 脚本 exit code 0 = 成功(允许有跳过项,只要无错误);非 0 = 致命错误或目标不存在,简要说明并停止。

## 异常处理(脚本内置,无需 LLM 介入)

| status | 处理 |
|--------|------|
| `completed` / `superseded` | 正常归档 |
| `open` / `pending` | **直接跳过** + 报告原因为"未完成的条目不能归档" |
| `in-progress` | 默认跳过,提示用户加 `--force` 重跑 |
| 非标准值 / frontmatter 缺失 | 跳过 + 报告原因 |
| archive 目录已有同名 | 自动加 `.YYYYMMDD_HHMMSS` 时间戳后缀,重命名归档 |

frontmatter 改动:`status: archived` + `archived_at: <now>` + `updated_at: <now>`。
移动失败时回滚 frontmatter。

## 什么时候才走 LLM

实际几乎用不到。仅当用户描述模糊(如"把那个跟 mint 有关的旧 todo 归档"),需要先识别具体文件路径再交给脚本时,才用 Read/Glob 定位后再调脚本。一旦定位到具体文件/feature 名,**立即转脚本**,不要在 LLM 流程里手工改 frontmatter + mv。

## 注意事项

1. 归档不可逆(文件从工作目录消失)。归档前建议先跑 `/rpiv-loop:flow-status` 或 `archive <target> --dry-run` 确认。
2. 归档后文件仍可通过 git 历史查看原始版本。
3. 只处理有 frontmatter 的 .md 文件,无 frontmatter 跳过。

## 退出码

- `0` 正常完成(可含跳过项)
- `1` 用户参数错误 / 文件或 feature 不存在
- `2` rpiv/ 目录缺失
