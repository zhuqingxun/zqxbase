# /// script
# requires-python = ">=3.11"
# dependencies = ["python-pptx>=1.0.0", "lxml>=4.9"]
# ///
"""codex_ppt.py: codex presentations 整本生成线的确定性封装外壳.

codex 产线本身是黑盒 (gpt-5.5 + presentations 插件), 本脚本把外围工程全部
确定性化: 可用性检测 -> run 目录 -> prompt 组装落盘 -> stdin 文件句柄喂 codex
-> 启动特征码校验 -> 超时杀进程树 + 孤儿清理 -> 产物目标态验证 -> manifest 落盘.

CLI 契约 (PRD §10):
    uv run --script scripts/codex_ppt.py --input <源材料目录> --output-dir <输出目录> \\
        [--topic <主题>] [--pages 12-15] [--timeout-min 45] [--style-constraints <文本>] \\
        [--style-ref <pptx路径>] [--codex-cmd codex] [--skip-detect]

    exit 0: 成功, stdout 最后一行 = PPTX 绝对路径 (正斜杠)
    exit 1: codex 运行失败 (stderr: 原因 + 已清理进程数)
    exit 2: 可用性检测失败 / 用法错误 (stderr: 缺什么)
    exit 3: 产物验证失败 (文件缺失/损坏/页数超界)

实现契约来源: ~/.claude/knowledge/codex.md 三坑 (stdin 喂 prompt / 禁加 --sandbox /
孤儿清理) + 2026-06-12 实测 (last.txt 反斜杠路径 / 启动特征码).
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 退出码常量 (镜像 engine/orchestrator.py 模式)
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ARTIFACT = 3

_ISO_FMT = "%Y-%m-%dT%H:%M:%S"
_RUNDIR_TS_FMT = "%Y%m%d-%H%M%S"

# 启动特征码: codex exec 正常启动时前 30 行必同时出现这两段 (实测锚定)
BANNER_STDIN = "Reading prompt from stdin"
BANNER_VERSION = "OpenAI Codex v"


def _now_iso() -> str:
    return datetime.now().strftime(_ISO_FMT)


def _fwd(path: Path | str) -> str:
    """路径归一化为正斜杠字符串."""
    return str(path).replace("\\", "/")


def _split_cmd(cmd: str) -> list[str]:
    """shlex.split(posix=False) + 剥除成对引号.

    posix=False 保留 Windows 反斜杠但不剥引号 — 带空格路径若被引号包裹,
    字面引号会进 token 导致 Popen WinError 2, 这里统一剥掉.
    """
    tokens: list[str] = []
    for t in shlex.split(cmd, posix=False):
        if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
            t = t[1:-1]
        tokens.append(t)
    return tokens


# =====================================================================
# 各步骤可单测的纯函数 / 小函数
# =====================================================================


def parse_pages(pages: str) -> tuple[int, int]:
    """'12-15' -> (12, 15); '14' -> (14, 14). 非法输入抛 ValueError."""
    if "-" in pages:
        lo_s, hi_s = pages.split("-", 1)
        lo, hi = int(lo_s), int(hi_s)
    else:
        lo = hi = int(pages)
    if lo < 1 or hi < lo:
        raise ValueError(f"非法页数范围: {pages}")
    return lo, hi


def build_prompt(
    input_dir: Path,
    output_dir: Path,
    topic: str,
    page_range: tuple[int, int],
    style_ref: Path | None,
    style_constraints: str | None,
) -> str:
    """组装整本线 prompt (模板固化在 references/codex-engine.md, 与实测基线一致)."""
    style_ref_clause = ""
    if style_ref is not None:
        style_ref_clause = (
            f"可参考 {_fwd(style_ref)} 的版式与配色风格 (仅作风格参考, 不强制对齐)。"
        )
    extra = ""
    if style_constraints:
        extra = style_constraints.rstrip("。") + "。"
    return (
        f"使用 presentations 技能, 读取 {_fwd(input_dir)} 下全部 markdown 源材料, "
        f"生成一本中文汇报 PPT: 主题是{topic}, {page_range[0]}-{page_range[1]} 页, "
        f"浅色底商务风格 (白底/浅蓝, 避免黑色或深色满底)。"
        f"{style_ref_clause}{extra}"
        f"最终 PPTX 输出到 {_fwd(output_dir)} 目录。完成后只回复最终 pptx 的绝对路径。"
    )


def new_run_dir(output_dir: Path) -> Path:
    """建 `<output-dir>/.ppt-workdir/runs/<YYYYMMDD-HHMMSS>-codex/` (撞名加毫秒)."""
    base = output_dir / ".ppt-workdir" / "runs"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime(_RUNDIR_TS_FMT)
    run_dir = base / f"{ts}-codex"
    if run_dir.exists():
        run_dir = base / f"{ts}-{datetime.now().microsecond:06d}-codex"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_detect(codex_cmd: str) -> tuple[bool, str, str | None]:
    """subprocess 调同目录 detect_codex.py. 返回 (可用, 失败原因, codex_version)."""
    detect_script = Path(__file__).resolve().parent / "detect_codex.py"
    # detect 只对可执行体本身有意义, 多 token --codex-cmd (测试注入) 传首 token
    tokens = _split_cmd(codex_cmd)
    if not tokens:
        return False, "--codex-cmd 为空", None
    try:
        proc = subprocess.run(
            [sys.executable, str(detect_script), "--codex-cmd", tokens[0]],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "detect_codex.py 执行超时 (60s)", None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, f"detect_codex.py 输出非 JSON: {proc.stdout[:200]}", None
    if proc.returncode == 0 and payload.get("available"):
        return True, "", payload.get("codex_version")
    return False, payload.get("reason", "未知原因"), None


def _read_head_lines(log_path: Path, n: int) -> str:
    """读日志前 n 行 (errors=replace 防 codex 非 UTF-8 输出崩溃)."""
    if not log_path.exists():
        return ""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readline() for _ in range(n))
    except OSError:
        return ""


def wait_banner(log_path: Path, proc: subprocess.Popen, banner_timeout_s: float) -> bool:
    """轮询日志, 等启动特征码 (前 30 行同时含两段特征). 超时或进程提前退出且无特征码 -> False."""
    deadline = time.monotonic() + banner_timeout_s
    while time.monotonic() < deadline:
        head = _read_head_lines(log_path, 30)
        if BANNER_STDIN in head and BANNER_VERSION in head:
            return True
        if proc.poll() is not None:
            # 进程已退出: 终态再判一次
            head = _read_head_lines(log_path, 30)
            return BANNER_STDIN in head and BANNER_VERSION in head
        time.sleep(0.5)
    return False


def cleanup_orphans(scope_hint: str) -> int:
    """防御性清理孤儿进程. 失败不阻塞, 返回清理数.

    双条件匹配: CommandLine 须同时含 'codex' 与本次 run 目录 (codex 命令行带
    `-C <run_dir>`) — 单匹配 'codex' 会误杀用户并行的其他合法 codex 会话.
    """
    if sys.platform != "win32":
        return 0
    hint = scope_hint.replace("'", "''")
    ps_cmd = (
        f"$hint = [regex]::Escape('{hint}'); "
        "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
        "Where-Object { $_.CommandLine -match 'codex' -and $_.CommandLine -match $hint } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )
        return len([ln for ln in proc.stdout.splitlines() if ln.strip().isdigit()])
    except Exception:
        return 0


def kill_tree(proc: subprocess.Popen, scope_hint: str) -> int:
    """杀进程树 + 防御性孤儿清理, 返回额外清理的孤儿数."""
    if sys.platform == "win32":
        # taskkill /T 杀整棵树 (uv -> python / npm shim -> node 链)
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, timeout=30,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    return cleanup_orphans(scope_hint)


def resolve_pptx_path(last_txt: Path, output_dir: Path, start_ts: float) -> Path | None:
    """定位 codex 产出的 PPTX: 优先 last.txt 回复路径 (实测反斜杠格式, Path 归一化),
    缺失/不可解析时 glob 输出目录 mtime > start 的最新 .pptx 兜底."""
    if last_txt.exists():
        text = last_txt.read_text(encoding="utf-8", errors="replace")
        for line in reversed(text.splitlines()):
            candidate = line.strip().strip('"').strip("'").strip("`")
            if candidate.lower().endswith(".pptx"):
                p = Path(candidate)
                if p.exists():
                    return p
    candidates = [
        p for p in output_dir.glob("*.pptx")
        if p.stat().st_mtime > start_ts
    ]
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NORMALIZE_PART_RE = r"ppt/(slides|notesSlides|slideLayouts|slideMasters|notesMasters)/[^/]+\.xml"


def _normalize_part_xml(data: bytes) -> tuple[bytes, int]:
    """修复单个 slide 类部件的已知 OOXML 不合规点, 返回 (新字节, 修复数)."""
    from lxml import etree

    root = etree.fromstring(data)
    fixed = 0

    # 1. cNvPr id 部件内去重 (codex 生成器每页都把 spTree 根与首 shape 都编为 1)
    cnvprs = [e for e in root.iter() if etree.QName(e).localname == "cNvPr"]
    ids = [int(e.get("id", "0")) for e in cnvprs]
    next_id = (max(ids) if ids else 0) + 1
    seen: set[int] = set()
    for e in cnvprs:
        i = int(e.get("id", "0"))
        if i in seen or i == 0:
            e.set("id", str(next_id))
            next_id += 1
            fixed += 1
        else:
            seen.add(i)

    # 2. a:ext 负尺寸归一化 (schema 要求 >=0; 平移 off 保持几何区域不变)
    for ext in root.iter(f"{{{_A_NS}}}ext"):
        if ext.get("uri") is not None:  # a:extLst 的 a:ext, 不是尺寸
            continue
        parent = ext.getparent()
        off = parent.find(f"{{{_A_NS}}}off") if parent is not None else None
        for dim, pos in (("cx", "x"), ("cy", "y")):
            raw = ext.get(dim)
            if raw is None:
                continue
            v = int(raw)
            if v < 0:
                if off is not None and off.get(pos) is not None:
                    off.set(pos, str(int(off.get(pos)) + v))
                ext.set(dim, str(-v))
                fixed += 1

    if not fixed:
        return data, 0
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), fixed


def normalize_pptx(pptx_path: Path) -> int:
    """修复 codex 生成器的已知 OOXML 不合规点 (PowerPoint 「需要修复」提示的根因).

    2026-06-12 E2E 实测: codex presentations 产出的每页都有 cNvPr id 重复,
    个别 shape 有负 ext 尺寸 — python-pptx/LibreOffice 容忍, PowerPoint 弹修复.
    确定性后处理, 返回总修复数.
    """
    import re as _re
    import zipfile

    total = 0
    tmp = pptx_path.with_suffix(".pptx.normtmp")
    try:
        with zipfile.ZipFile(pptx_path) as src, \
                zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for item in src.infolist():
                data = src.read(item.filename)
                if _re.fullmatch(_NORMALIZE_PART_RE, item.filename):
                    data, n = _normalize_part_xml(data)
                    total += n
                out.writestr(item, data)
        if total:
            pptx_path.unlink()
            tmp.rename(pptx_path)
        else:
            tmp.unlink()
    except BaseException:
        # 原文件还在 (unlink 前失败 / 被 PowerPoint 锁定) 时清掉半成品 tmp;
        # 原文件已删而 rename 失败的极端情况保留 tmp 兜数据
        if pptx_path.exists():
            tmp.unlink(missing_ok=True)
        raise
    return total


def verify_artifact(pptx_path: Path, page_range: tuple[int, int]) -> tuple[bool, str, int]:
    """目标态验证: python-pptx 可打开 + 页数在范围内 (含边界). 返回 (通过, 原因, 页数)."""
    from pptx import Presentation
    try:
        pres = Presentation(str(pptx_path))
        n_slides = len(pres.slides)
    except Exception as exc:
        return False, f"PPTX 打开失败: {pptx_path}: {exc}", 0
    lo, hi = page_range
    if not (lo <= n_slides <= hi):
        return False, f"页数 {n_slides} 超出要求范围 {lo}-{hi}", n_slides
    return True, "", n_slides


def _plugin_version() -> str | None:
    plugin_json = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    try:
        return json.loads(plugin_json.read_text(encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError):
        return None


def write_manifest(run_dir: Path, payload: dict) -> None:
    (run_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# =====================================================================
# 主流程
# =====================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="codex presentations 整本生成线封装")
    parser.add_argument("--input", required=True, help="源材料目录 (markdown)")
    parser.add_argument("--output-dir", required=True, help="PPTX 输出目录")
    parser.add_argument("--topic", default=None, help="主题 (默认从输入目录名推断)")
    parser.add_argument("--pages", default="12-15", help="页数范围, 如 12-15 或 14")
    parser.add_argument("--timeout-min", type=float, default=45, help="总超时 (分钟)")
    parser.add_argument("--style-constraints", default=None, help="附加风格约束文本")
    parser.add_argument("--style-ref", default=None, help="风格参考 PPTX 路径 (软性注入)")
    parser.add_argument("--codex-cmd", default="codex", help="codex 命令 (可含参数, 测试注入用)")
    parser.add_argument("--skip-detect", action="store_true", help="跳过可用性检测 (测试用)")
    parser.add_argument(
        "--banner-timeout-s", type=float, default=90,
        help="启动特征码等待上限 (秒, 默认 90)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_dir.is_dir():
        print(f"输入目录不存在: {input_dir}", file=sys.stderr)
        return EXIT_USAGE
    try:
        page_range = parse_pages(args.pages)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    # Step 1: 可用性检测
    codex_version: str | None = None
    if not args.skip_detect:
        ok, reason, codex_version = run_detect(args.codex_cmd)
        if not ok:
            print(f"codex 不可用: {reason}", file=sys.stderr)
            return EXIT_USAGE

    # Step 2: run 目录
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = new_run_dir(output_dir)

    # Step 3: prompt 组装落盘 (UTF-8 显式)
    topic = args.topic or input_dir.name
    style_ref: Path | None = None
    if args.style_ref:
        candidate = Path(args.style_ref).resolve()
        if candidate.exists():
            style_ref = candidate
        else:
            print(f"警告: --style-ref 文件不存在, 忽略: {candidate}", file=sys.stderr)
    prompt = build_prompt(
        input_dir, output_dir, topic, page_range, style_ref, args.style_constraints,
    )
    prompt_path = run_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    manifest: dict = {
        "schema_version": "1.0",
        "engine": "codex",
        "plugin_version": _plugin_version(),
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "duration_s": None,
        "input": _fwd(input_dir),
        "prompt_file": "prompt.txt",
        "codex_version": codex_version,
        "style_ref": _fwd(style_ref) if style_ref else None,
        "pptx_path": None,
        "pptx_pages": None,
        "pptx_bytes": None,
        "normalized_fixes": None,
        "exit_status": None,
    }

    def finish(exit_code: int, fail_reason: str | None = None, cleaned: int = 0) -> int:
        manifest["finished_at"] = _now_iso()
        if start_monotonic is not None:
            manifest["duration_s"] = round(time.monotonic() - start_monotonic, 1)
        manifest["exit_status"] = exit_code
        write_manifest(run_dir, manifest)
        if fail_reason:
            print(f"{fail_reason} (已清理孤儿进程数: {cleaned})", file=sys.stderr)
        return exit_code

    # Step 4: 调用 codex (stdin = prompt 文件句柄, 绝不传 --sandbox)
    last_txt = run_dir / "last.txt"
    log_path = run_dir / "codex-log.txt"
    cmd_tokens = _split_cmd(args.codex_cmd)
    if not cmd_tokens:
        print("--codex-cmd 为空", file=sys.stderr)
        return EXIT_USAGE
    # Windows 下 Popen 不做 PATHEXT 解析, npm shim (codex.cmd) 必须 which 出完整路径
    resolved = shutil.which(cmd_tokens[0])
    if resolved:
        cmd_tokens[0] = resolved
    cmd = cmd_tokens + [
        "exec", "--skip-git-repo-check",
        "-C", str(run_dir),
        "-o", str(last_txt),
    ]
    start_monotonic: float | None = None
    manifest["started_at"] = _now_iso()
    start_ts = time.time()
    start_monotonic = time.monotonic()
    try:
        with open(prompt_path, "rb") as prompt_fh, open(log_path, "wb") as log_fh:
            proc = subprocess.Popen(
                cmd,
                stdin=prompt_fh,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=str(run_dir),
            )
    except OSError as exc:
        return finish(EXIT_FAIL, f"codex 启动失败: {exc}")

    # Step 5: 启动特征码校验
    banner_budget = min(args.banner_timeout_s, args.timeout_min * 60)
    if not wait_banner(log_path, proc, banner_budget):
        cleaned = 0
        if proc.poll() is None:
            cleaned = kill_tree(proc, str(run_dir))
        return finish(
            EXIT_FAIL,
            f"codex 启动特征码缺失 ({banner_budget:.0f}s 内未见 "
            f"'{BANNER_STDIN}' + '{BANNER_VERSION}'), 日志: {_fwd(log_path)}",
            cleaned,
        )

    # Step 6: 超时守护
    remaining = max(1.0, args.timeout_min * 60 - (time.monotonic() - start_monotonic))
    try:
        proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        cleaned = kill_tree(proc, str(run_dir))
        return finish(
            EXIT_FAIL,
            f"codex 超时 ({args.timeout_min} 分钟), 已杀进程树",
            cleaned,
        )
    if proc.returncode != 0:
        # 进程已自然退出, 不做全局孤儿扫描 (防误杀并行 codex 会话)
        return finish(
            EXIT_FAIL,
            f"codex 退出码非 0: {proc.returncode}, 日志: {_fwd(log_path)}",
        )

    # Step 7: 目标态验证 (仅 exit 0 不算成功)
    pptx_path = resolve_pptx_path(last_txt, output_dir, start_ts)
    if pptx_path is None:
        return finish(
            EXIT_ARTIFACT,
            f"未找到产出 PPTX: last.txt 无可用路径且 {_fwd(output_dir)} 下无新 .pptx",
        )
    # Step 7.5: OOXML 规范化 (codex 生成器已知缺陷, 不修 PowerPoint 会弹「需要修复」)
    try:
        manifest["normalized_fixes"] = normalize_pptx(pptx_path)
    except Exception as exc:
        # 规范化失败不阻塞 (产物仍可用, 只是 PowerPoint 可能提示修复)
        manifest["normalized_fixes"] = None
        print(f"警告: OOXML 规范化失败, 跳过: {exc}", file=sys.stderr)
    ok, reason, n_slides = verify_artifact(pptx_path, page_range)
    if not ok:
        manifest["pptx_path"] = _fwd(pptx_path.resolve())
        manifest["pptx_pages"] = n_slides or None
        return finish(EXIT_ARTIFACT, f"产物验证失败: {reason}")

    # Step 8: manifest + stdout 最后一行 = PPTX 绝对路径
    pptx_abs = pptx_path.resolve()
    manifest["pptx_path"] = _fwd(pptx_abs)
    manifest["pptx_pages"] = n_slides
    manifest["pptx_bytes"] = pptx_abs.stat().st_size
    finish(EXIT_OK)
    print(_fwd(pptx_abs))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
