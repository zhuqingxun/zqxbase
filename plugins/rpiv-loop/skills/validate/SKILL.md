---
name: rpiv-loop:validate
description: >-
  根据项目结构自动选择 lint、测试、构建及可选服务检查，并输出摘要
allowed-tools: Read, Bash, Grep, Glob
version: 2.1.5
---

# 运行项目的全面验证

按项目类型执行验证并报告。优先采用项目自定义的验证方式，否则根据检测到的技术栈自动选择 lint、测试、构建及可选的服务健康检查。

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

- 存在 `pytest` 或 `[tool.pytest]` → `pytest -v`（若 CLAUDE/README 有约定如 `-m "not slow"` 则加上）；若无 pytest 有 `unittest` → `python -m unittest discover`；均无则跳过并注明

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

## 摘要报告

所有验证（及可选的服务检查）完成后，提供包含以下内容的摘要报告：

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
