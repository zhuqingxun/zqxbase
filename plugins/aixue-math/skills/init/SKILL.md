---
name: aixue-math:init
description: >-
  aixue-math 工作区初始化命令——在指定目录创建 .aixue/workspace.yaml 工作区标识文件和 6 个子目录骨架
  (01_教材 / 02_知识点 / 03_写作要求 / 04_教案样例 / 05_教案 / 06_板书)。通过 AskUserQuestion 引导用户填写
  课时名 / 年级 / 教材版本 / 课型。当用户说「初始化工作区」「aixue-math:init」「新建数学教案工作区」
  「建一个周长课的工作区」时触发。这是所有 aixue-math 流水线使用的前置步骤：未 init 的目录运行
  aixue-math:textbook / generate / status 等会报错。
allowed-tools: Read, Write, Bash, AskUserQuestion
version: 0.5.2
---

# aixue-math:init — 工作区初始化

> **路径约定**：`{AIXUE_MATH_REF}` = aixue-math 插件 `references/` 目录，`{AIXUE_MATH_SCRIPTS}` = 同级 `scripts/` 目录。
> 首次引用时通过 `Glob("**/plugins/aixue-math/references/workspace-schema.md")` 定位，多结果时优先非 `marketplaces/` 路径。

## 用法

```
/aixue-math:init [课时名]
```

- **带参数**：`/aixue-math:init 周长_什么是周长` —— 课时名作为第一个参数。
- **不带参数**：通过 AskUserQuestion 引导用户输入课时名。

工作区默认创建在 `<项目根>/workspaces/<NN>_<课时名>/` 下。项目根按优先级探测：① 环境变量 `$AIXUE_MATH_PROJECT`；② 从 cwd 向上找已含 `workspaces/` 目录的祖先；③ 都没有则用 `$PWD`。

### 目录命名：`NN_<课时名>` 序号前缀（强制）

课题目录一律带两位序号前缀，例 `workspaces/01_周长_什么是周长/`。序号的唯一作用是**让文件管理器里按建立先后排序、便于索引**：

| 位置 | 是否带序号 | 例 |
|------|-----------|-----|
| `workspaces/` 下的课题目录 | ✅ 带 | `01_周长_什么是周长/` |
| `_dist/` 下的成品目录（镜像 workspaces） | ✅ 带 | `_dist/01_周长_什么是周长/` |
| `workspace.yaml` 的 `workspace.name` | ❌ **不带** | `周长_什么是周长` |
| `workspace.yaml` 的 `workspace.title` | ❌ 不带（本就是课题标题） | `什么是周长` |
| 教案 md frontmatter 的 `lesson_workspace` | ❌ 不带（取自 `name`） | `周长_什么是周长` |

**序号单调追加，绝不重排既有编号** —— 新课题永远取「当前最大序号 + 1」，即使中间有空档或年级不连续。重排会让所有既有的 `dist_dir`、文档引用、交付链接同时失效，收益远小于代价。

## 执行流程

### 第一步：前置检查

1. **检查课时名是否通过参数提供**：
   - 如果没有提供参数，进入第二步先获取课时名。
   - 如果提供了，直接进入第三步。

2. **确定项目根**：
   ```bash
   # 项目根探测: ① $AIXUE_MATH_PROJECT ② 向上找已含 workspaces/ 的祖先 ③ cwd
   PROJECT_ROOT="${AIXUE_MATH_PROJECT:-}"
   if [ -z "$PROJECT_ROOT" ]; then
     CURRENT="$PWD"
     while [ "$CURRENT" != "/" ] && [ "$CURRENT" != "$(dirname "$CURRENT")" ]; do
       if [ -d "$CURRENT/workspaces" ]; then
         PROJECT_ROOT="$CURRENT"; break
       fi
       CURRENT="$(dirname "$CURRENT")"
     done
   fi
   # 未找到则使用 cwd（首个课时会在此新建 workspaces/）
   [ -z "$PROJECT_ROOT" ] && PROJECT_ROOT="$PWD"
   ```

   **注意**：此时还不能拼出 `WORKSPACE_ROOT` —— 目录名要带序号前缀，序号由下一步算。

3. **分配序号并拼出工作区目标路径**（拿到课时名之后执行，不带参数时在第二步之后）：
   ```bash
   uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py next-seq \
     "$PROJECT_ROOT/workspaces" --name "<课时名>"
   ```

   返回 JSON：`{"seq":"05","name":"<课时名>","dir_name":"05_<课时名>","workspace_root":"<绝对路径>","dist_dir":"../../_dist/05_<课时名>"}`。

   取其 `workspace_root` 作为 `WORKSPACE_ROOT`，取 `name`（已剥掉用户可能误带的序号前缀）作为传给 init-workspace 的课时名。**不要自己数目录拼序号** —— `next-seq` 已处理空目录、无前缀目录、序号空档等边界。

4. **目标路径已存在 .aixue/workspace.yaml**：
   ```bash
   test -f "$WORKSPACE_ROOT/.aixue/workspace.yaml"
   ```
   若存在 → 输出 `工作区已初始化: <WORKSPACE_ROOT>，如需修改请直接编辑 .aixue/workspace.yaml` 并 exit 1。

### 第二步：AskUserQuestion（课时名 + 年级 + 教材版本 + 课型）

**当 1 次** AskUserQuestion 调用，包含 4 题（根据是否已通过参数提供课时名，最多 4 题最少 3 题）。

**Q1 — 课时名（仅当未提供参数时）**
- question: `课时名是什么？（目录名会自动加 NN_ 序号前缀）`
- header: `课时名`
- multiSelect: `false`
- options（3 个示例 + 自动 Other 兜底）：
  - label: `周长_什么是周长` — description: `三年级下册"什么是周长"课时的命名示例`
  - label: `周长_长方形的周长` — description: `命名约定：<单元>_<课题>`
  - label: `认识时间_时分秒` — description: `二年级下册"时、分、秒"课时的命名示例`

说明：课时名应使用下划线 `_` 分隔（避免空格，Windows 路径友好），**且不要自己写序号前缀** —— 序号由 `next-seq` 统一分配，用户误填的 `01_` 会被自动剥掉。用户几乎总会选 Other 填写自己的课时名。

**Q2 — 年级**
- question: `这节课对应哪个年级？`
- header: `年级`
- multiSelect: `false`
- options（4 个最常用）：
  - label: `三年级上册` — description: `小学三年级第一学期`
  - label: `三年级下册` — description: `小学三年级第二学期`
  - label: `四年级上册` — description: `小学四年级第一学期`
  - label: `四年级下册` — description: `小学四年级第二学期`

其他年级通过 Other 兜底（如"一年级上册"、"六年级下册"）。

**Q3 — 教材版本**
- question: `使用哪个教材版本？`
- header: `教材版本`
- multiSelect: `false`
- options（4 个主流版本）：
  - label: `北师大版` — description: `北京师范大学出版社`
  - label: `人教版` — description: `人民教育出版社`
  - label: `苏教版` — description: `江苏凤凰教育出版社`
  - label: `西师大版` — description: `西南师范大学出版社`

**Q4 — 课型**
- question: `本课时的课型是什么？`
- header: `课型`
- multiSelect: `false`
- options（4 类标准课型）：
  - label: `新授课` — description: `讲授新概念、新知识的课（本类最常见）`
  - label: `练习课` — description: `以巩固练习为主的课`
  - label: `复习课` — description: `对已学知识进行系统回顾的课`
  - label: `综合实践课` — description: `数学应用 / 跨学科 / 项目式学习`

### 第三步：构造参数并调用 workspace_io.py init-workspace

将 AskUserQuestion 返回的答案组装为 CLI 参数：

```bash
uv run --script {AIXUE_MATH_SCRIPTS}/workspace_io.py init-workspace \
  "$WORKSPACE_ROOT" \
  "<课时名>" \
  "<年级>" \
  "<教材版本>" \
  --lesson-type "<课型>" \
  --shared-dir "../../shared"
```

参数说明：
- `<WORKSPACE_ROOT>` 是 `next-seq` 返回的 `workspace_root`（末段已含 `NN_` 序号前缀）
- `<课时名>` **不带序号**，写进 workspace.yaml 的 `workspace.name`；目录名里的序号由路径末段承载，两者刻意不一致
- `dist_dir` 不用显式传：`init-workspace` 自动取 `../../_dist/<工作区目录名>`（连序号一起），使 `_dist/` 与 `workspaces/` 目录一一镜像
- `<课型>` 默认"新授课"；如果 AskUserQuestion 被取消，使用默认值

成功返回 JSON：`{"workspace_yaml": "<绝对路径>", "workspace_root": "<绝对路径>"}`。失败 exit 非 0 并在 stderr 输出 `ERROR: ...`。

### 第四步：验证写入结果

```bash
test -f "$WORKSPACE_ROOT/.aixue/workspace.yaml" && \
  grep -q '^workspace:' "$WORKSPACE_ROOT/.aixue/workspace.yaml"
```

失败立即报告错误。

再验证 6 个子目录（含 2 个链接）都存在：

```bash
test -d "$WORKSPACE_ROOT/01_教材/docs" && \
test -d "$WORKSPACE_ROOT/01_教材/extracted" && \
test -d "$WORKSPACE_ROOT/02_知识点/docs" && \
test -d "$WORKSPACE_ROOT/02_知识点/extracted" && \
test -e "$WORKSPACE_ROOT/03_写作要求" && \
test -e "$WORKSPACE_ROOT/04_教案样例" && \
test -d "$WORKSPACE_ROOT/05_教案/md" && \
test -d "$WORKSPACE_ROOT/05_教案/docx" && \
test -d "$WORKSPACE_ROOT/05_教案/html" && \
test -d "$WORKSPACE_ROOT/05_教案/pdf" && \
test -d "$WORKSPACE_ROOT/06_板书"
```

注意 `03_写作要求/` 和 `04_教案样例/` 默认是 junction（Windows）或 symlink（Unix）指向 `shared/` 下的对应目录 —— 保证"目录看起来完整、内容共享"。若用户环境不允许创建链接，会 fallback 为普通目录 + README 说明。init-workspace 输出的 JSON 含 `shared_links` 字段告知每个链接创建结果。

### 第五步：检查 shared/ 是否已填充

```bash
ls "$PROJECT_ROOT/shared/03_写作要求/" 2>/dev/null | grep -v README
ls "$PROJECT_ROOT/shared/04_教案样例/samples/" 2>/dev/null | grep -v README
```

如果两个目录都只有 README（即 shared 资源还没填充），在末尾引导块中提醒用户：**生成教案前需要先填充 shared/03_写作要求/ 和 shared/04_教案样例/**。

### 第六步：输出引导块

```markdown
---
## 工作区已创建

📁 `workspaces/<NN>_<课时名>/`
   ├── .aixue/workspace.yaml       ← 元数据（可手动编辑细化 unit/title/duration 等）
   ├── 01_教材/                    输入 (1) — 待处理
   ├── 02_知识点/                  输入 (2) — 待处理
   ├── 05_教案/{md,docx,html,pdf}/  输出 (5a) 教案最新版 — 待生成（历史进 OLD/）
   ├── 06_板书/                    输出 (5b) 板书 — 待生成

## 下一步

推荐: `/aixue-math:textbook <PDF 路径> <起始页> <结束页>`
原因: 工作区刚初始化，下一步提取教材 (输入 1) 以启动流水线。

其他选择:
- `/aixue-math:status`: 查看当前工作区状态
- `/aixue-math:next`: 获取智能下一步引导
- 手动编辑 `.aixue/workspace.yaml`: 补充 title、unit、duration_minutes 等可选字段

# 如果 shared/ 未填充，追加：
⚠ 提示: shared/03_写作要求/ 和 shared/04_教案样例/ 尚未填充。建议在生成教案前
  补充这两个目录的内容（通用教学规范 + 优质教案样例），否则 aixue-math:generate
  无法正常运行。
```

## 异常处理

| 情况 | 处理 |
|------|------|
| 目标路径已存在 workspace.yaml | 报错 `工作区已初始化: <路径>` + exit 1 |
| AskUserQuestion 被用户取消 | 不创建任何文件，输出已取消消息 + exit 0 |
| init-workspace 脚本返回错误 | 透传 stderr，exit 1 |
| 课时名包含非法字符（空格 / 中文标点） | 提示用户用下划线替换空格、移除标点后重试 |
| 用户在课时名里自带了 `01_` 之类前缀 | `next-seq` 自动剥掉，按当前最大序号重新分配，不产生 `01_01_xxx` |
| `workspaces/` 下混有无序号的历史目录 | `next-seq` 只统计带 `NN_` 前缀的目录；无序号目录不参与计数，也**不自动改名**（改名是人工决策，见下方非目标） |

## 非目标（禁止扩展）

- 不自动提取教材 PDF（由 `aixue-math:textbook` 单独处理）
- 不自动填充 shared/（用户手动补充或通过专门的资源管理 skill）
- 不尝试创建软链接到 shared/（Windows 兼容性问题，通过 workspace.yaml 的 `shared_dir` 字段解决）
- 不校验 shared/ 是否已填充（仅在末尾引导块提醒；填充与否不影响 init 成功）
- **不给既有课题目录批量补/改序号**，也不重排已有编号 —— 存量改名会连带 `dist_dir`、`_dist/` 目录、文档引用一起动，属人工决策，不在 init 职责内

## 参考文档

- `{AIXUE_MATH_REF}/workspace-schema.md` — workspace.yaml 完整 schema
