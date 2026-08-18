---
name: rpiv-loop:validate
description: >-
  根据项目结构自动选择 lint、测试、构建及可选服务检查，并输出摘要
allowed-tools: Read, Bash, Edit, Grep, Glob
version: 2.17.14
---

> `<rpiv-loop-root>` 解析顺序：环境变量 `RPIV_LOOP_ROOT` -> `CLAUDE_PLUGIN_ROOT` -> 当前插件根目录；均不存在时停止并请用户配置 `RPIV_LOOP_ROOT` 或 `CLAUDE_PLUGIN_ROOT`。

# 运行项目的全面验证

按项目类型执行验证并报告。优先采用项目自定义的验证方式，否则根据检测到的技术栈自动选择 lint、测试、构建及可选的服务健康检查。

---

## 第 0 步：项目级 DoD gates（rpiv/dod.yaml）

**若存在 `rpiv/dod.yaml`**（由 rpiv-loop 入口 skill 幂等创建、用户按项目修订），先读取其 `gates` 逐条执行，再继续后续验证流程（本步不短路「优先级 0」与「按类型检测」）：

1. 命令型 `verification_method` → 运行并记录退出码；与后续步骤将执行的命令相同时（如 `uv run pytest`）只跑一次，复用结果
2. `verification_method: manual_review` → 不自动执行，在摘要报告中列为「人工确认」项
3. 命令因工具/脚本缺失无法执行 → 该 gate 记为失败，并提示用户修订 dod.yaml（模板允许删除或替换不适用条目）
4. **判定**：任一 `blocking: true` 的 gate 失败 → 整体健康评估记为**失败**；非 blocking gate 失败仅记警告
5. 不存在 `rpiv/dod.yaml` → 跳过本步，不视为异常

执行结果在「摘要报告」的「DoD gates」小节逐条列出（gate id / blocking / 通过与否 / 证据摘要）。

---

## 第 0.5 步：产物类型分派（skill 分支入口）

**PRD 定位规则**：复用本文件「AC 逐条证据采集」章节已确立的 `<feature>` 输入契约——该契约的路径是 `rpiv/validation/<feature>/acceptance.yaml`，本步同构地读取 `rpiv/requirements/prd-<feature>.md` 的 frontmatter `product_types` 字段。**不引入任何新的"如何确定当前 feature"机制。**

**两种缺省一律静默回落 `[code]`**——不报错、不中断流程、不在报告中标记为异常：

1. PRD 文件存在但无 `product_types` 字段 → 按 `[code]`（存量 PRD 无需回填）
2. 按约定路径找不到 PRD 文件 → 按 `[code]`。**这不是理论情况**：PRD 归档后会被移动到 `rpiv/archive/`，约定路径就此失效，任何已交付归档的历史特性再跑 validate 都会命中这条

分派规则：

1. **含 `skill`** → 执行 skill 验证分支：Read `<rpiv-loop-root>/references/skill-authoring/skill-validation-checklist.md`，按其通用质量门与分层验收清单逐项验收，结果记入「摘要报告」新增的「skill 质量门」小节
2. **含 `code`** → 继续下方「优先级 0」与「按类型检测与执行」，行为不变
3. **`[code, skill]`** → 两条分支**都执行**，摘要报告分节呈现，互不遮蔽
4. **纯 `[skill]`（不含 `code`）** → **跳过**下方「优先级 0」与「按类型检测与执行」的代码侧流程，直接进入「摘要报告」。此时代码检查 / 测试 / 覆盖率 / 构建各项一律标注「**不适用（纯 skill 产物）**」，**不得**输出「未执行自动验证」——纯 Markdown 产物落入 3.7 节「其他 / 未识别」而整体标为未验证，正是本分派要消除的空转

**本步不被「优先级 0」短路**：即使项目命中了自定义验证入口（脚本 / Make / 包管理器 script），skill 分支仍须执行——「优先级 0」的「直接进入摘要报告」只作用于代码侧验证流程。

---

## 优先级 0：项目自定义

**先依次检查，若存在则按该方式执行，并直接进入文末「摘要报告」；否则继续「按类型检测与执行」。**

1. **脚本**：`./scripts/validate.sh`、`./scripts/validate`（或 Windows 下 `.cmd`、`.ps1`）
2. **Make**：`make validate`（若存在 Makefile 且包含 validate 目标）
3. **包管理器入口**：`npm run validate`、`pnpm validate`、`uv run validate`（或 pyproject 的 `[project.scripts]` 中的 validate）
4. **项目内命令定义**：`项目/.claude/commands/validation/validate.md` 或 `docs/validate-commands.md`（若存在，按其中步骤执行）
5. **CLAUDE.md / README**：若在「验证命令」「测试」「常用命令」等章节中**明确列出**用于验证的完整命令序列（如 `pytest -m "not slow"`、`ruff check .`），则按该序列执行

---

## 按类型检测与执行

若优先级 0 均未命中，先检测项目结构，再按类型执行。

### 3.1 检测项目结构

通过 `ls`、`test -f`、`git ls-files` 等查找：

- `pyproject.toml`、`requirements.txt`、`setup.py` → 视为含 **Python**
- `package.json`（根目录或 `frontend/`、`packages/*`）→ 视为含 **Node/前端**
- `go.mod`、`Cargo.toml` → 视为 **Go**、**Rust**
- `backend/`、`frontend/`、`src/`、`packages/` → 用于确定工作目录

### 3.2 Python

- **工作目录**：若存在 `backend/` 则 `backend/`，否则 `src/`（若存在），否则项目根
- **运行方式**：若项目使用 uv（存在 `uv.lock` 或 `pyproject.toml` 中 `[tool.uv]` 等），优先 `uv run <cmd>`；否则 `python -m` 或 `pip` 安装后直接命令

**Lint**（按存在性选择其一，**均无则跳过并注明**）：

- 存在 `[tool.ruff]`、`ruff.toml` 或项目常用 ruff → `uv run ruff check .` 或 `ruff check .`
- 存在 `[tool.flake8]` 或 `.flake8` → `flake8 .` 或 `flake8 <常用目录>`
- 存在 pylint 配置 → `pylint <目标模块或目录>`

**Test**：

- 存在 `pytest` 或 `[tool.pytest]` → 按上方「运行方式」选择 `uv run pytest -v` 或 `pytest -v`（若 CLAUDE/README 有约定如 `-m "not slow"` 则加上）；若无 pytest 有 `unittest` → 按上方「运行方式」选择 `uv run python -m unittest discover` 或 `python -m unittest discover`；均无则跳过并注明

**Coverage**：

- 若 `[tool.coverage]` 或项目惯用 `--cov`，运行 `pytest --cov=<包名> --cov-report=term-missing`；否则**可选**跳过

### 3.3 Node / 前端

- **工作目录**：`frontend/`、`packages/frontend` 或 根（若仅有一个 `package.json`）
- **包管理器**：若存在 `pnpm-lock.yaml` 用 `pnpm`，否则 `npm`

**Lint**：若 `package.json` 的 `scripts` 中有 `lint` → `npm run lint` 或 `pnpm lint`；否则跳过并注明

**Test**：若 `scripts` 中有 `test` → `npm test` 或 `pnpm test`；否则跳过

**Build**：若 `scripts` 中有 `build` → `npm run build` 或 `pnpm build`；否则跳过

### 3.4 多组件（如 backend + frontend）

- 先对 **backend**（按 3.2 若为 Python，或按 3.3 若为 Node）在对应工作目录下执行
- 再对 **frontend** 按 3.3 执行
- 若根目录的 `package.json` 仅为 monorepo 根、无实质代码，不重复跑根目录的 lint/test

### 3.5 Go

在工作目录（含 `go.mod` 的目录或根）执行：

```bash
go build ./...
go test ./...
```

### 3.6 Rust

在工作目录（含 `Cargo.toml` 的目录或根）执行：

```bash
cargo build
# 或 cargo check
cargo test
```

### 3.7 其他 / 未识别

若未识别到 Python/Node/Go/Rust 的常见结构，注明：「未自动识别到常见技术栈，请参考 README、CLAUDE.md 或 CI（如 .github/workflows）中的验证步骤」。可仅输出报告，整体标为「未执行自动验证」。

---

## 可选：服务健康检查

- **条件**：CLAUDE.md 或 README 中**明确写出**启动命令（如 `uvicorn xxx:app --port 8765`、`npm run dev`）以及健康或文档 URL（如 `/health`、`/docs`、`http://localhost:8765/...`）
- **步骤**：按文档启动（后台），等待 2–5 秒后请求该 URL，根据状态码判断通过/失败
- **停止**：若文档未要求长期运行，验证后可尝试停止：
  - **Windows**：`taskkill /F /IM <进程名>` 或按端口查进程后结束
  - **Unix**：`lsof -ti:<端口> | xargs kill -9` 或 `pkill -f <可识别子串>`
  - 若无法可靠停止或存在权限/环境差异，可**不执行停止**，只在报告中写明「已进行健康检查，请必要时手动停止服务」
- **未写明**：跳过并注明「未发现启动命令与健康检查 URL，已跳过服务验证」

---

## AC 逐条证据采集（强约束）

**输入契约**：`rpiv/validation/<feature>/acceptance.yaml`（由 plan-feature 阶段产出骨架，已含 `id / given / when / then / verification_method / blocking`）。

**本阶段职责**：对 `acceptance.yaml` 中的每一条 AC，执行其 `verification_method` 并**逐条填写 `evidence` 与 `status`**。

### 操作步骤

1. **读取 acceptance.yaml**：通过 `Read` 工具载入全部 AC 条目
2. **逐条执行 `verification_method`**：
   - 命令型（如 `uv run pytest ...`）→ 运行并捕获输出
   - 脚本型（如 `bash tests/integration/*.sh`）→ 运行并记录退出码
   - 可视/手工型（如 smoke screenshot）→ 产生截图后登记路径
3. **翻 `status`**：
   - `passed`：执行成功且证据充分
   - `failed`：执行失败或证据与 `then` 断言不符
   - `not_applicable`：环境不支持（此时 `notes` 必须说明理由）
4. **填 `evidence`**（**禁止模糊文本**）：
   - 测试类：`tests/test_xxx.py::test_name` 或 `tests/test_xxx.py:123`
   - 命令类：关键 stdout/stderr 片段（≤ 200 字符）或完整输出文件路径
   - 日志类：`logs/validate-<date>.log` 的行号片段
   - 截图类：`docs/screenshots/<feature>-ac-NNN.png`
   - **反例**：`evidence: "已测"`、`evidence: "OK"`、`evidence: "通过"` — 这类一律视为 failed

### 禁止修改的字段

本阶段**只能**动 `evidence / status / notes` 三个字段。以下字段是 plan 阶段产出的契约，validate 阶段**禁止改动**：

- `id` — 唯一标识
- `given / when / then` — Gherkin 三段
- `verification_method` — 验证手段
- `blocking` — 强/软约束标记

如发现 plan 阶段的 AC 本身有问题（措辞模糊、验证方法不可执行），回退到 plan-feature 阶段修订，不要在 validate 阶段绕过。

### 完成后校验

本阶段结束前**必须**运行：

```bash
uv run --no-project python <rpiv-loop-root>/tools/check_acceptance.py <feature>
```

- 退出码 `0` → 所有 blocking AC 均 passed 或 not_applicable（且 evidence/notes 非空）→ 可进入 delivery-report
- 退出码 `1` → 有 blocking AC 未过，按输出清单补齐
- 退出码 `2` → 文件缺失或 YAML 格式错误，修文件后重跑

---

## 摘要报告

所有验证（及可选的服务检查）完成后，提供包含以下内容的摘要报告：

- **DoD gates**：逐条列出 `rpiv/dod.yaml` 的 gate 结果（id / blocking / 通过与否 / manual_review 项列为人工确认）；无 dod.yaml 时标注「未配置」
- **skill 质量门**：产物类型含 `skill` 时，逐条列出通用质量门与分层验收结果（未含 skill 时标注「不适用」）
- **代码检查（Lint）**：通过 / 失败 / 未执行（及原因）
- **测试**：通过 / 失败 / 未执行（及原因）
- **覆盖率**：百分比或「未执行」（若执行了带 coverage 的测试）
- **构建**：通过 / 失败 / 未执行（若执行了 build）
- **服务健康检查**：通过 / 失败 / 未执行（若执行了）
- **错误或警告**：列出的具体信息
- **整体健康评估**：**通过** / **失败**

使用清晰标题和状态符号（如 ✓/✗ 或 通过/失败）格式化。

---

## 跨平台与边界说明

- **工作目录**：所有 `cd` 与命令均在上述「工作目录」下执行；多组件时分别 `cd` 到 backend 与 frontend。
- **杀进程 / 停服务**：仅在「可选：服务健康检查」中涉及；若环境难以可靠杀进程，以「报告 + 提示用户手动停止」代替，不要求必须成功杀进程。
- **存在性判断**：通过 `test -f`、`ls`、`cat package.json | grep scripts` 等可脚本化方式判断，避免主观假定。
