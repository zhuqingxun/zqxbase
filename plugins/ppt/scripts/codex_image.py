# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow>=10.0"]
# ///
"""codex_image.py: codex imagegen 视觉素材生成的确定性封装外壳.

调用 codex (gpt-5.5 内置 image_gen, 免 OPENAI_API_KEY) 生成浅色调摄影感
封面图 / 章节配图, 供 renderer cover 版式的 image_ref 消费.

结构与 codex_ppt.py 镜像 (检测 -> prompt 落文件 -> Popen stdin -> 特征码 ->
超时杀树 -> 目标态验证), 两脚本刻意各自独立实现不抽公共模块 (可单独移动分发).

CLI 契约 (PRD §10):
    uv run --script scripts/codex_image.py --theme <deck主题描述> --output <png绝对路径> \\
        [--kind cover|section] [--timeout-min 10] [--codex-cmd codex] [--skip-detect]

    exit 0: 成功, stdout 最后一行 = PNG 绝对路径 (正斜杠)
    exit 1: codex 运行失败 (stderr: 原因 + 已清理孤儿进程数)
    exit 2: 可用性检测失败 / 用法错误
    exit 3: 产物验证失败 (PNG 缺失 / 损坏 / 短边 < 800px)
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

# 防 decompression bomb (照抄 engine/parse.py 的上限)
from PIL import Image
Image.MAX_IMAGE_PIXELS = 50_000_000

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ARTIFACT = 3

_ISO_FMT = "%Y-%m-%dT%H:%M:%S"

# 启动特征码 (与 codex_ppt.py 同源, 实测锚定)
BANNER_STDIN = "Reading prompt from stdin"
BANNER_VERSION = "OpenAI Codex v"

# 目标态验证: 短边像素下限
MIN_SHORT_SIDE_PX = 800

_KIND_SPEC = {
    "cover": ("封面背景图", "左侧约 40% 区域保持简洁纯净, 供标题文字叠放"),
    "section": ("章节过渡配图", "中部区域保持简洁"),
}


def _now_iso() -> str:
    return datetime.now().strftime(_ISO_FMT)


def _fwd(path: Path | str) -> str:
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


def build_prompt(theme: str, kind: str, output_png: Path) -> str:
    """组装生图 prompt (模板固化在 references/codex-engine.md)."""
    kind_desc, blank_hint = _KIND_SPEC[kind]
    return (
        f"生成一张「{theme}」主题的{kind_desc}: 浅色调, 真实摄影感, 商务风格, "
        f"画面构图留白充足 ({blank_hint}), 避免深色满幅、避免画面中出现任何文字。"
        f"直接保存为 {_fwd(output_png)}, 完成后只回复保存路径。"
    )


def run_detect(codex_cmd: str) -> tuple[bool, str]:
    """subprocess 调同目录 detect_codex.py."""
    detect_script = Path(__file__).resolve().parent / "detect_codex.py"
    # detect 只对可执行体本身有意义, 多 token --codex-cmd (测试注入) 传首 token
    tokens = _split_cmd(codex_cmd)
    if not tokens:
        return False, "--codex-cmd 为空"
    try:
        proc = subprocess.run(
            [sys.executable, str(detect_script), "--codex-cmd", tokens[0]],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "detect_codex.py 执行超时 (60s)"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, f"detect_codex.py 输出非 JSON: {proc.stdout[:200]}"
    if proc.returncode == 0 and payload.get("available"):
        return True, ""
    return False, payload.get("reason", "未知原因")


def _read_head_lines(log_path: Path, n: int) -> str:
    if not log_path.exists():
        return ""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readline() for _ in range(n))
    except OSError:
        return ""


def wait_banner(log_path: Path, proc: subprocess.Popen, banner_timeout_s: float) -> bool:
    deadline = time.monotonic() + banner_timeout_s
    while time.monotonic() < deadline:
        head = _read_head_lines(log_path, 30)
        if BANNER_STDIN in head and BANNER_VERSION in head:
            return True
        if proc.poll() is not None:
            head = _read_head_lines(log_path, 30)
            return BANNER_STDIN in head and BANNER_VERSION in head
        time.sleep(0.5)
    return False


def cleanup_orphans(scope_hint: str) -> int:
    """防御性清理孤儿进程 (失败不阻塞).

    双条件匹配: CommandLine 须同时含 'codex' 与本次工作目录 (codex 命令行带
    `-C <work_dir>`) — 单匹配 'codex' 会误杀用户并行的其他合法 codex 会话.
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
    if sys.platform == "win32":
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


def verify_artifact(png_path: Path) -> tuple[bool, str]:
    """目标态验证: PNG 落盘 + Pillow 可打开 + 短边 >= 800px."""
    if not png_path.exists():
        return False, f"PNG 未落盘: {png_path}"
    try:
        with Image.open(png_path) as img:
            img.verify()
        with Image.open(png_path) as img:
            w, h = img.size
    except Exception as exc:
        return False, f"PNG 损坏/不可打开: {png_path}: {exc}"
    if min(w, h) < MIN_SHORT_SIDE_PX:
        return False, f"PNG 尺寸过小: {w}x{h} (短边须 >= {MIN_SHORT_SIDE_PX}px)"
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="codex imagegen 视觉素材封装")
    parser.add_argument("--theme", required=True, help="deck 主题描述")
    parser.add_argument("--output", required=True, help="PNG 输出绝对路径")
    parser.add_argument("--kind", choices=("cover", "section"), default="cover")
    parser.add_argument("--timeout-min", type=float, default=10, help="总超时 (分钟)")
    parser.add_argument("--codex-cmd", default="codex", help="codex 命令 (测试注入用)")
    parser.add_argument("--skip-detect", action="store_true", help="跳过可用性检测 (测试用)")
    parser.add_argument(
        "--banner-timeout-s", type=float, default=90,
        help="启动特征码等待上限 (秒, 默认 90)",
    )
    args = parser.parse_args()

    output_png = Path(args.output).resolve()
    if output_png.suffix.lower() != ".png":
        print(f"--output 必须是 .png 路径: {output_png}", file=sys.stderr)
        return EXIT_USAGE

    # Step 1: 可用性检测
    if not args.skip_detect:
        ok, reason = run_detect(args.codex_cmd)
        if not ok:
            print(f"codex 不可用: {reason}", file=sys.stderr)
            return EXIT_USAGE

    # Step 2: 工作目录 (与 PNG 同级 .codex-image-work, prompt/日志落此; 撞名加毫秒防同秒并发混写)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    base = output_png.parent / ".codex-image-work"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    work_dir = base / ts
    if work_dir.exists():
        work_dir = base / f"{ts}-{datetime.now().microsecond:06d}"
    work_dir.mkdir(parents=True, exist_ok=False)

    # Step 3: prompt 落盘 (UTF-8 显式)
    prompt = build_prompt(args.theme, args.kind, output_png)
    prompt_path = work_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    # Step 4: 调用 codex (stdin 文件句柄, 绝不传 --sandbox)
    last_txt = work_dir / "last.txt"
    log_path = work_dir / "codex-log.txt"
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
        "-C", str(work_dir),
        "-o", str(last_txt),
    ]
    start_monotonic = time.monotonic()
    try:
        with open(prompt_path, "rb") as prompt_fh, open(log_path, "wb") as log_fh:
            proc = subprocess.Popen(
                cmd,
                stdin=prompt_fh,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=str(work_dir),
            )
    except OSError as exc:
        print(f"codex 启动失败: {exc}", file=sys.stderr)
        return EXIT_FAIL

    # Step 5: 启动特征码校验
    banner_budget = min(args.banner_timeout_s, args.timeout_min * 60)
    if not wait_banner(log_path, proc, banner_budget):
        cleaned = kill_tree(proc, str(work_dir)) if proc.poll() is None else 0
        print(
            f"codex 启动特征码缺失 ({banner_budget:.0f}s), 日志: {_fwd(log_path)} "
            f"(已清理孤儿进程数: {cleaned})",
            file=sys.stderr,
        )
        return EXIT_FAIL

    # Step 6: 超时守护
    remaining = max(1.0, args.timeout_min * 60 - (time.monotonic() - start_monotonic))
    try:
        proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        cleaned = kill_tree(proc, str(work_dir))
        print(
            f"codex 超时 ({args.timeout_min} 分钟), 已杀进程树 (已清理孤儿进程数: {cleaned})",
            file=sys.stderr,
        )
        return EXIT_FAIL
    if proc.returncode != 0:
        # 进程已自然退出, 不做全局孤儿扫描 (防误杀并行 codex 会话)
        print(
            f"codex 退出码非 0: {proc.returncode}, 日志: {_fwd(log_path)}",
            file=sys.stderr,
        )
        return EXIT_FAIL

    # Step 7: 目标态验证
    ok, reason = verify_artifact(output_png)
    if not ok:
        print(f"产物验证失败: {reason}", file=sys.stderr)
        return EXIT_ARTIFACT

    print(_fwd(output_png))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
