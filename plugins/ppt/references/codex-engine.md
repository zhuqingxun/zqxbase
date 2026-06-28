# codex 引擎参考 (ppt-codex-fusion)

/ppt 的 codex 引擎线: 用 codex CLI (gpt-5.5 + presentations 插件 + 内置 imagegen) 生成编辑级 deck 与视觉素材。codex 产线本身是黑盒, 外围工程 (检测 / 调用 / 验证 / 清理) 全部由 `scripts/` 下三个确定性脚本封装。**SKILL.md 层只做引擎路由与交互编排, 禁止手写裸 `codex exec`**。

## 1. 调用契约 (三脚本 CLI)

### detect_codex.py — 可用性检测

```
uv run --script <plugin-root>/scripts/detect_codex.py [--codex-cmd codex]

exit 0: 可用, stdout JSON {"available": true, "codex_version": "X.Y.Z", "presentations": true}
exit 1: 不可用, stdout JSON {"available": false, "reason": "<具体缺什么>"}
```

检测四项: CLI 存在 / 版本可解析 (`codex-cli X.Y.Z`) / auth.json 存在 (只查存在性, 不读内容) / config.toml 中 `presentations@*` 插件 enabled=true。CODEX_HOME 环境变量优先于 `~/.codex`。

### codex_ppt.py — 整本生成线

```
uv run --script <plugin-root>/scripts/codex_ppt.py --input <源材料目录> --output-dir <输出目录> \
    [--topic <主题>] [--pages 12-15] [--timeout-min 45] [--style-constraints <文本>] \
    [--style-ref <pptx路径>] [--codex-cmd codex] [--skip-detect]

exit 0: 成功, stdout 最后一行 = PPTX 绝对路径 (正斜杠)
exit 1: codex 运行失败 (stderr: 原因 + 已清理孤儿进程数)
exit 2: 可用性检测失败 / 用法错误 (stderr: 缺什么)
exit 3: 产物验证失败 (文件缺失 / 损坏 / 页数超界)
```

内部流程 (全确定性): 检测 → run 目录 (`<输出目录>/.ppt-workdir/runs/<时间戳>-codex/`) → prompt 组装落盘 → stdin 文件句柄喂 codex → 启动特征码校验 (90s 内须见 `Reading prompt from stdin` + `OpenAI Codex v`) → 超时杀进程树 + 孤儿清理 → 目标态验证 (python-pptx 可打开 + 页数在界内) → manifest.json 落盘 (engine=codex)。

### codex_image.py — imagegen 素材线

```
uv run --script <plugin-root>/scripts/codex_image.py --theme <deck主题描述> --output <png绝对路径> \
    [--kind cover|section] [--timeout-min 10] [--codex-cmd codex] [--skip-detect]

exit 0: 成功, stdout 最后一行 = PNG 绝对路径
exit 1/2/3: 同 codex_ppt 语义 (3 = PNG 缺失 / 损坏 / 短边 < 800px)
```

## 2. prompt 模板 (固化文本, 改动须同步 codex_ppt.py / codex_image.py 的 build_prompt)

### 整本线

```
使用 presentations 技能, 读取 {input_dir} 下全部 markdown 源材料, 生成一本中文汇报 PPT: 主题是{topic}, {page_min}-{page_max} 页, 浅色底商务风格 (白底/浅蓝, 避免黑色或深色满底)。{style_ref_clause}{extra_constraints}最终 PPTX 输出到 {output_dir} 目录。完成后只回复最终 pptx 的绝对路径。
```

| 变量 | 来源 | 说明 |
|---|---|---|
| `{input_dir}` | `--input` | 正斜杠绝对路径 |
| `{topic}` | `--topic`, 默认输入目录名 | |
| `{page_min}-{page_max}` | `--pages` (默认 12-15) | 单值 `14` 视为 `14-14` |
| `{style_ref_clause}` | `--style-ref` 提供且文件存在时注入 | 固定措辞: `可参考 {style_ref} 的版式与配色风格 (仅作风格参考, 不强制对齐)。` |
| `{extra_constraints}` | `--style-constraints` 提供时注入 | 原文 + `。` |
| `{output_dir}` | `--output-dir` | 正斜杠绝对路径 |

### 生图线

```
生成一张「{theme}」主题的{kind_desc}: 浅色调, 真实摄影感, 商务风格, 画面构图留白充足 ({blank_hint}), 避免深色满幅、避免画面中出现任何文字。直接保存为 {output_png}, 完成后只回复保存路径。
```

| `--kind` | `{kind_desc}` | `{blank_hint}` |
|---|---|---|
| cover | 封面背景图 | 左侧约 40% 区域保持简洁纯净, 供标题文字叠放 |
| section | 章节过渡配图 | 中部区域保持简洁 |

## 3. 坑清单 (封装脚本已内置规避, 列出供排障)

1. **prompt 必须从 stdin 喂**: `codex exec` 在非 TTY 环境检测到 stdin 重定向就读 stdin; prompt 当参数传 + stdin 不喂会卡住等输入 (实测卡 13 分钟零产出)。封装用 prompt 文件句柄直接做 Popen stdin。
2. **禁止传 `--sandbox`**: 用户 config 默认 `danger-full-access` (含网络); 自作主张加 `--sandbox workspace-write` 会禁网, 生成请求被沙箱挡死。封装绝不传该参数。
3. **Bash 单引号坑**: `'<prompt>' | codex exec` 只在 PowerShell 成立, Git Bash 会把 prompt 当命令执行。根治 = prompt 落 UTF-8 文件再喂 stdin (封装已做), SKILL.md 层永远不手写 shell 管道喂 prompt。
4. **孤儿进程**: codex 卡死时外层 shell 超时只杀 shell, node 子进程变孤儿继续耗资源/额度。封装超时用 `taskkill /F /T` 杀树 + 防御性扫描残留 node.exe — 扫描是**双条件匹配** (CommandLine 同时含 `codex` 与本次 run/work 目录), 不会误杀用户并行的其他 codex 会话; 进程自然退出 (非超时) 的失败路径不做全局扫描。
5. **last.txt 反斜杠路径**: codex 回复的产物路径为 Windows 反斜杠格式 (`D:\...`), 解析需 Path() 归一化; last.txt 缺失时 glob 输出目录 mtime 较新的 `.pptx` 兜底。
6. **仅 exit 0 不算成功**: codex 进程退出 0 不代表产物合格, 必须目标态验证 (文件真落盘 + python-pptx/Pillow 可打开 + 页数/尺寸在界内)。封装 exit 3 即此验证失败。
7. **启动特征码**: 正常启动的日志前 30 行必同时出现 `Reading prompt from stdin` 与 `OpenAI Codex v`。看不到 = 启动失败 (auth 失效 / CLI 损坏), 封装 90s 内未见即快速失败, 不傻等全额超时。
8. **codex 产物 OOXML 不合规 (PowerPoint 弹「需要修复」)**: codex presentations 生成器系统性产出两类 schema 违规 — 每页 cNvPr id 重复 (与 spTree 根同为 1) + 个别 shape 负 ext 尺寸。python-pptx / LibreOffice 容忍, PowerPoint 必弹修复提示。codex_ppt.py 的 normalize 后处理已确定性修复 (manifest 的 `normalized_fixes` 字段记录修复数); 若 PowerPoint 仍提示修复, 说明出现了新的违规类型, 用 lxml 扫描 slide XML 定位。
9. **Windows PATHEXT**: `Popen(["codex", ...])` 不解析 npm shim (`codex.cmd`), 报 WinError 2。封装已用 `shutil.which` 解析首 token; 任何新脚本调 codex 同样必须先 which。
10. **`--codex-cmd` 形态约定**: 多 token 形态 (如 `"uv run --script fake_codex.py"`) 是测试注入通道, 可用性检测只对首 token 有意义, 须搭配 `--skip-detect` 使用; 带空格路径需引号包裹, 封装已剥除成对引号 (`shlex.split(posix=False)` 不剥引号的坑已内置处理)。

## 4. 风格参考机制 (--style-ref)

- **语义**: 软性参考。prompt 措辞固定为「可参考 ... 的版式与配色风格 (仅作风格参考, 不强制对齐)」, 给 codex 设计自由度, **禁止改成强制对齐措辞**。
- **优先级**: 显式 `--style-ref <路径>` > 本机默认 > 无。`--no-style-ref` (SKILL.md 层参数) 强制不带。
- **本机默认值查找规则**: 默认参考文件的路径登记在用户全局 `~/.claude/knowledge/codex.md` (「ppt-codex-fusion 封装入口」节)。SKILL.md 编排时 Read 该文件取路径, **确认文件存在后**才传给 `--style-ref`。插件源码与本文档不存任何本机绝对路径 (参考文件可能是敏感材料, 且路径因机器而异)。
- `--style-ref` 指向不存在的文件时, codex_ppt.py 打 stderr 警告并忽略 (不阻塞)。

## 5. 对比报告模板 (--compare 用)

`--compare` 编排完成后, 按此模板落 `<输出目录>/compare-report.md`:

```markdown
# /ppt:create 双引擎对比报告

- **输入**: <输入路径>
- **Timestamp**: <ISO 8601>

## 汇总

| 引擎 | taste layout 均分 | taste palette 均分 | 页数 | 耗时 | 文件大小 |
|---|---|---|---|---|---|
| codex (general 模式评审) | x.xx | x.xx | N | Xm Ys | X.X MB |
| renderer (anchor 模式评审) | x.xx | x.xx | N | Xm Ys | X.X MB |

(任一引擎失败时: 该行替换为「失败: <原因>」, 保留另一行)

## 结论建议

{2-4 句: 双轴分数对比定位 + 各自 Top 改进项 + 建议采用哪本/如何取长补短}

## 产物清单

- codex: <pptx 路径> + <taste 报告路径>
- renderer: <pptx 路径> + <taste 报告路径>
```

## 6. 引擎边界

- codex 线**不进** orchestrator 状态机 (无 state.json, 不支持 resume); 只镜像 manifest 字段风格供追溯。
- codex 是可选增强层: detect 失败时 /ppt:create 静默走 renderer 线 (这是路由不是降级, 零提示噪音); 显式 `--engine codex` 失败才报错停。
- 源材料会上传 OpenAI 云端 (codex 后端), SKILL.md 编排层负责数据出境告知与敏感路径确认。
