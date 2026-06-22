# /// script
# requires-python = ">=3.11"
# dependencies = ["python-pptx>=1.0.0", "pydantic>=2.0", "pyyaml>=6.0", "lxml>=4.9", "Pillow>=10.0"]
# ///
"""orchestrator.py: ppt 产线短命状态机 CLI (run / resume / replay).

把 ppt 产线 (parse -> architect gate -> validate_architecture -> plan gate ->
validate_plan -> render) 从"会话即兴串联"改造成命令式工程流程. 每次运行在
`.ppt-workdir/runs/<timestamp>/` 落盘全部阶段产物.

三种子命令:
- run <input>      : 会话桥接 mode. parse 后在 architect LLM gate 暂停 (exit 3 NEED_LLM),
                     会话产出 02-architect/output.yaml 后 resume.
- resume <run-dir> : 推进会话桥接. 校验当前 awaiting 的 output.yaml, 通过则推进到下一
                     gate (exit 3) 或终点 (exit 0); 校验失败写 error.json (exit 1).
- replay <input> --fixture <dir> : recorded mode. 固定 fixture 回放两个 LLM 阶段,
                     无暂停一口气跑完 (CI 0 LLM 依赖).

退出码 (§6.3):
- 0  : 成功 / 完成 (DONE)
- 1  : 校验失败 (validate_architecture / validate_plan / schema / render 失败)
- 2  : 用法错误 (无子命令 / 参数缺失)
- 3  : 需要会话 LLM 介入 (NEED_LLM, run/resume 在 LLM gate 暂停)

调度方式 = import (非 subprocess, 见 plan §决策 D1): validate_plan.py 顶层 import
`from schemas.variants` 在 sys.path 设置前, subprocess 直调会 ModuleNotFoundError.
orchestrator 启动先 sys.path.insert(PLUGIN_ROOT), 全程 import 调度 6 个阶段脚本.

LLM 智能保持在会话层: orchestrator 只做编排 + 归档 + 校验调度, 零 LLM 逻辑.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# PEP 723 standalone script: 在任何 `from engine.*` / `from schemas.*` import 之前
# 把 plugin 根目录推入 sys.path. 这是 validate_plan.py D1 陷阱 (schemas 顶层 import) 的根治.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

# 退出码常量 (§6.3)
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_NEED_LLM = 3

# 时间戳格式 (run 目录名必须匹配 \d{8}-\d{6}, TC-A1)
_RUNDIR_TS_FMT = "%Y%m%d-%H%M%S"
# ISO 8601 时间戳 (manifest/state 字段)
_ISO_FMT = "%Y-%m-%dT%H:%M:%S"

_STAGE_NAMES = ("parse", "architect", "plan", "render")


# =====================================================================
# 内部工具: plugin 版本 / 时间戳 / sha256
# =====================================================================


def _plugin_version() -> str:
    """从 .claude-plugin/plugin.json 读 version (不硬编码, 避免漂移)."""
    pj = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    return str(data.get("version", "0.0.0"))


def _now_iso() -> str:
    return datetime.now().strftime(_ISO_FMT)


def _parse_target_files(path: Path) -> list[Path]:
    """返回会被 parse 处理的文件列表 (与 parse.main 的扫描规则一致, 用于 sha256).

    parse.main: 文件直接用; 目录 rglob('*') 后取 .md/.png/.jpg/.jpeg/.svg.
    """
    if path.is_file():
        return [path]
    parse_exts = {".md", ".png", ".jpg", ".jpeg", ".svg"}
    files = [f for f in sorted(path.rglob("*")) if f.is_file() and f.suffix.lower() in parse_exts]
    return files


def _sha256_input(path: Path) -> str:
    """计算输入指纹 (64 hex 小写).

    目录: 对所有受 parse 的文件按相对路径排序逐个 hash 串接再 hash.
    文件: 单文件 hash.
    """
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    # 目录: 按相对路径排序, 逐文件 hash 串接再 hash
    files = _parse_target_files(path)
    pairs = sorted((str(f.relative_to(path)).replace("\\", "/"), f) for f in files)
    outer = hashlib.sha256()
    for rel, f in pairs:
        outer.update(rel.encode("utf-8"))
        outer.update(hashlib.sha256(f.read_bytes()).hexdigest().encode("ascii"))
    return outer.hexdigest()


# =====================================================================
# 任务 2: run 目录 + manifest / state / error 读写工具
# =====================================================================


def _new_run_dir(output_dir: str | Path) -> Path:
    """建 `.ppt-workdir/runs/<YYYYMMDD-HHMMSS>/` + 5 个子目录.

    时间戳精度到秒, 高频两次 run 可能撞名 → 撞名时加毫秒后缀防撞.
    """
    base = Path(output_dir) / ".ppt-workdir" / "runs"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime(_RUNDIR_TS_FMT)
    run_dir = base / ts
    if run_dir.exists():
        # 撞名: 加毫秒后缀 (run 目录名仍以 \d{8}-\d{6} 开头, TC-A1 用 startswith/前 15 字符匹配)
        ts = datetime.now().strftime(_RUNDIR_TS_FMT) + f"-{datetime.now().microsecond:06d}"
        run_dir = base / ts
    run_dir.mkdir(parents=True, exist_ok=False)
    for sub in ("01-parse", "02-architect", "03-plan", "04-render", "05-taste"):
        (run_dir / sub).mkdir()
    return run_dir


def _dump_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _init_manifest(
    run_dir: Path,
    *,
    mode: str,
    input_path: str,
    input_sha256: str,
    input_kind: str,
    preset: str,
    theme: str,
    output_path: str,
    taste_requested: bool,
) -> dict:
    """初始化 manifest (字段名严格按 §JSON Schema 冻结)."""
    manifest = {
        "schema_version": "1.0",
        "plugin_version": _plugin_version(),
        "mode": mode,
        "created_at": _now_iso(),
        "input": input_path,
        "input_sha256": input_sha256,
        "input_kind": input_kind,
        "preset": preset,
        "theme": theme,
        "output_path": output_path,
        "taste_requested": taste_requested,
        "stages": {
            name: {"status": "pending", "started_at": None, "finished_at": None}
            for name in _STAGE_NAMES
        },
    }
    _write_manifest(run_dir, manifest)
    return manifest


def _write_manifest(run_dir: Path, manifest: dict) -> None:
    _dump_json(run_dir / "manifest.json", manifest)


def _read_manifest(run_dir: Path) -> dict:
    return _load_json(run_dir / "manifest.json")


def _stage_start(run_dir: Path, manifest: dict, stage: str) -> None:
    manifest["stages"][stage]["status"] = "running"
    manifest["stages"][stage]["started_at"] = _now_iso()
    _write_manifest(run_dir, manifest)


def _stage_done(run_dir: Path, manifest: dict, stage: str) -> None:
    manifest["stages"][stage]["status"] = "completed"
    manifest["stages"][stage]["finished_at"] = _now_iso()
    _write_manifest(run_dir, manifest)
    # M1: 阶段成功完成 = 系统在前进, 归档前一次失败残留的 error.json (避免与 done 矛盾)
    _clear_error_on_success(run_dir)


def _stage_failed(run_dir: Path, manifest: dict, stage: str) -> None:
    manifest["stages"][stage]["status"] = "failed"
    manifest["stages"][stage]["finished_at"] = _now_iso()
    _write_manifest(run_dir, manifest)


def _ensure_taste_stage(manifest: dict) -> None:
    """taste 是可选末阶段, 不进 _STAGE_NAMES (避免污染非-taste run 的 manifest).

    仅在真正进入 taste gate / replay-taste 时惰性插入 stages.taste, 让 _stage_*
    helper 能索引到该 key. 非-taste run 的 manifest 永远只含 4 个确定性阶段.
    """
    manifest["stages"].setdefault(
        "taste", {"status": "pending", "started_at": None, "finished_at": None}
    )


def _record_taste_result(run_dir: Path, manifest: dict, report) -> None:
    """把校验通过的 TasteReport 双轴均分 + AP 计数落 manifest.taste_result (下游机读)."""
    manifest["taste_result"] = {
        "report_path": "05-taste/taste-report.json",
        "mode": report.mode,
        "pages": report.pages,
        "layout_avg": report.summary.layout_avg,
        "palette_avg": report.summary.palette_avg,
        "antipattern_count": len(report.antipattern_hits),
    }
    _write_manifest(run_dir, manifest)


def _write_state(
    run_dir: Path,
    *,
    current_stage: str,
    awaiting: str | None,
    mode: str,
    next_action: str,
    expected_schema: str | None,
) -> None:
    state = {
        "current_stage": current_stage,
        "awaiting": awaiting,
        "mode": mode,
        "next_action": next_action,
        "expected_schema": expected_schema,
    }
    _dump_json(run_dir / "state.json", state)


def _read_state(run_dir: Path) -> dict:
    return _load_json(run_dir / "state.json")


def _write_error(
    run_dir: Path,
    *,
    stage: str,
    slide_no: int | None,
    rule: str | None,
    message: str,
    remediation: str,
) -> None:
    error = {
        "stage": stage,
        "slide_no": slide_no,
        "rule": rule,
        "message": message,
        "remediation": remediation,
    }
    _dump_json(run_dir / "error.json", error)


def _clear_error_on_success(run_dir: Path) -> None:
    """stage 成功推进时归档残留 error.json (M1).

    resume 失败→修复→成功后, 旧 error.json 与 state.json(done) 矛盾, 人工排查易误判.
    改名为 error-resolved-<n>.json 保留追溯 (不直接删, 便于复盘失败-恢复轨迹).
    """
    err = run_dir / "error.json"
    if not err.exists():
        return
    n = 1
    while (run_dir / f"error-resolved-{n}.json").exists():
        n += 1
    err.rename(run_dir / f"error-resolved-{n}.json")


# =====================================================================
# 阶段调度 (import, 见 D1)
# =====================================================================


def _run_parse(run_dir: Path, input_path: str) -> Path:
    """调度 parse stage. 返回 parsed-content.json 路径.

    预检 Path.exists() 防 parse.main 在路径不存在时 sys.exit 杀进程 (research §1.7).
    """
    from engine.parse import main as parse_main  # noqa: PLC0415

    out_json = run_dir / "01-parse" / "parsed-content.json"
    parse_main(input_path, str(out_json))
    return out_json


def _validate_architecture_to_json(run_dir: Path, arch: dict, preset_name: str) -> list[str]:
    """调度 validate_architecture, 写 02-architect/validation.json, 返回 issues.

    内容质量 issues 是 advisory (team-lead 2026-06-11 裁决): 完整记录到 validation.json
    + stderr 打 warning, 但不 fail (调用方不据此 exit 1). 质量把关交给用户确认 gate +
    Stage 3 validate_plan 两道既有硬门.
    """
    from engine.architect import load_preset, validate_architecture  # noqa: PLC0415

    preset = load_preset(preset_name)
    issues = validate_architecture(arch, preset)
    _dump_json(
        run_dir / "02-architect" / "validation.json",
        {"issues": issues, "advisory": True},
    )
    if issues:
        print(
            f"[orchestrator] WARNING (advisory, 不阻塞): validate_architecture 报 {len(issues)} 条内容质量 issue, "
            f"已记入 02-architect/validation.json. 建议复核但不阻塞推进:",
            file=sys.stderr,
        )
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
    return issues


def _assemble_theme_prompt(run_dir: Path, theme_name: str) -> Path:
    """调度 assemble_stage3_prompt(mode='file'), 写 03-plan/theme-prompt.md."""
    from engine.plan import load_theme  # noqa: PLC0415
    from engine.prompt_assembler import assemble_stage3_prompt  # noqa: PLC0415

    theme = load_theme(theme_name)
    theme_prompt_path = run_dir / "03-plan" / "theme-prompt.md"
    assemble_stage3_prompt(theme, "file", str(theme_prompt_path))
    return theme_prompt_path


def _validate_plan_to_json(run_dir: Path, plan_yaml_path: Path):
    """调度 validate_plan, 写 03-plan/validation.json, 返回 ValidationReport."""
    from engine.validate_plan import validate_plan  # noqa: PLC0415

    report = validate_plan(str(plan_yaml_path))
    _dump_json(run_dir / "03-plan" / "validation.json", report.to_dict())
    return report


def _load_theme_thresholds(theme_name: str) -> tuple[float, float]:
    from engine.validate_plan import load_theme_thresholds as _lt  # noqa: PLC0415  (S4 L4 公有化)

    return _lt(theme_name)


def _safe_copy_output(src: Path, dst: Path) -> Path:
    """拷贝渲染产物到 dst, 被占用 (PermissionError) 时自动落 dst_v2..v9 (M2).

    全局 Windows 防锁规范: 输出 pptx 常被用户正在查看的 Office 锁定. 整个 run 的 deck
    其实已渲染成功, 不该因最终一步 copyfile 被锁而把 run 标 failed.
    返回实际落点 (供 render-log / 调用方记录真实路径).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(src, dst)
        return dst
    except PermissionError:
        for v in range(2, 10):
            alt = dst.with_name(f"{dst.stem}_v{v}{dst.suffix}")
            try:
                shutil.copyfile(src, alt)
                print(
                    f"[orchestrator] WARNING: 输出 {dst.name} 被占用 (Office?), 已落 {alt.name}",
                    file=sys.stderr,
                )
                return alt
            except PermissionError:
                continue
        raise  # v2..v9 全被占用, fail-loud


def _run_render(run_dir: Path, plan_yaml_path: Path, theme_name: str, output_path: str) -> Path:
    """调度 render. 返回 04-render/deck.pptx 路径, 同时拷到 output_path."""
    from engine.render import render_presentation, load_theme, _resolve_image_refs  # noqa: PLC0415
    from schemas.slide_plan import SlidePlan  # noqa: PLC0415

    plan = SlidePlan.from_yaml(str(plan_yaml_path))
    _resolve_image_refs(plan, plan_yaml_path.resolve().parent)
    theme = load_theme(theme_name)
    deck_path = run_dir / "04-render" / "deck.pptx"
    render_presentation(plan, theme, str(deck_path))
    if not deck_path.exists():
        # render_presentation 在 PermissionError 时可能存到 _v2..v9; 取字典序最新落点 (L3)
        alt = sorted(deck_path.parent.glob("deck_v*.pptx"))
        if alt:
            deck_path = alt[-1]
    # 拷到 --output (M2: 被锁自动 _vN fallback, 记录真实落点)
    actual_out = _safe_copy_output(deck_path, Path(output_path))
    # render-log.json
    from engine.render import _RENDERERS  # noqa: PLC0415

    _dump_json(
        run_dir / "04-render" / "render-log.json",
        {
            "renderers_loaded": len(_RENDERERS),
            "slides_rendered": len(plan.slides),
            "output_path": str(actual_out),
            "size_bytes": deck_path.stat().st_size,
        },
    )
    return deck_path


# =====================================================================
# prompt-context 组装 (会话桥接)
# =====================================================================


def _summarize_parsed_content(parsed_json_path: Path) -> str:
    """从 parsed-content.json 生成 architect prompt 的输入摘要 (assets + 各 source heading 大纲)."""
    data = _load_json(parsed_json_path)
    assets = data.get("assets", {})
    lines = [
        f"- 总文件数: {assets.get('total_files', '?')}",
        f"- 文本源: {assets.get('text_sources', '?')}",
        f"- 图片资产: {assets.get('image_assets', '?')}",
        f"- 估计内容量: {assets.get('estimated_content_volume', '?')}",
        "",
        "各源材料大纲 (heading):",
    ]
    for src in data.get("sources", []):
        fname = Path(str(src.get("file", "?"))).name
        lines.append(f"\n### {fname} ({src.get('type', '?')})")
        headings = [
            b for b in src.get("content_blocks", []) if b.get("type") == "heading"
        ]
        if headings:
            for h in headings[:30]:
                indent = "  " * max(0, int(h.get("level", 1)) - 1)
                lines.append(f"{indent}- {h.get('text', '')}")
        else:
            lines.append("  (无 heading)")
    return "\n".join(lines)


def _format_preset_structure(preset: dict) -> str:
    sections = preset.get("structure", {}).get("required_sections", [])
    if not sections:
        return "(无 required_sections)"
    out = []
    for s in sections:
        role = s.get("role", "")
        title = s.get("title", "")
        out.append(f"- role={role} {title}".rstrip())
    return "\n".join(out)


def _format_preset_content_rules(preset: dict) -> str:
    rules = preset.get("content_rules", {})
    if not rules:
        return "(无 content_rules)"
    return "\n".join(f"- {k}: {v}" for k, v in rules.items())


def _write_architect_prompt_context(
    run_dir: Path, parsed_json_path: Path, preset_name: str, output_path: str
) -> Path:
    """组装 02-architect/prompt-context.md (plan §模板 1)."""
    from engine.architect import load_preset  # noqa: PLC0415

    preset = load_preset(preset_name)
    parsed_summary = _summarize_parsed_content(parsed_json_path)
    preset_structure = _format_preset_structure(preset)
    preset_content_rules = _format_preset_content_rules(preset)
    design_guide = (PLUGIN_ROOT / "design-guide.md").read_text(encoding="utf-8")
    arch_output = str(run_dir / "02-architect" / "output.yaml")

    ctx = _ARCHITECT_PROMPT_TEMPLATE.format(
        output_path=arch_output,
        parsed_content_summary=parsed_summary,
        preset_name=preset_name,
        preset_structure=preset_structure,
        preset_content_rules=preset_content_rules,
        design_guide_text=design_guide,
        plugin_root=str(PLUGIN_ROOT),
        run_dir=str(run_dir),
    )
    ctx_path = run_dir / "02-architect" / "prompt-context.md"
    ctx_path.write_text(ctx, encoding="utf-8")
    return ctx_path


def _summarize_architecture(arch: dict) -> str:
    """从 02-architect/output.yaml 生成 plan prompt 的架构摘要 (thesis + chapters 大纲)."""
    lines = [
        f"**核心论点 (thesis)**: {arch.get('thesis', '')}",
        f"**目标受众**: {arch.get('target_audience', '')}",
        f"**叙事弧线 (arc)**: {arch.get('arc', '')}",
        f"**预计总页数**: {arch.get('total_slides', '?')}",
        "",
        "**章节大纲**:",
    ]
    for ch in arch.get("chapters", []):
        lines.append(f"\n- 章节: {ch.get('title', '')}")
        lines.append(f"  核心信息: {ch.get('key_message', '')}")
        briefs = ch.get("slide_briefs", [])
        for b in briefs:
            st = b.get("slide_title", "")
            vt = b.get("visual_type_hint", "")
            lines.append(f"    - {st} [{vt}]")
    return "\n".join(lines)


def _write_plan_prompt_context(
    run_dir: Path, arch: dict, theme_name: str, theme_prompt_path: Path, output_path: str
) -> Path:
    """组装 03-plan/prompt-context.md (plan §模板 2)."""
    arch_summary = _summarize_architecture(arch)
    plan_output = str(run_dir / "03-plan" / "output.yaml")

    ctx = _PLAN_PROMPT_TEMPLATE.format(
        architecture_summary=arch_summary,
        theme_name=theme_name,
        theme_prompt_path=str(theme_prompt_path),
        plugin_root=str(PLUGIN_ROOT),
        run_dir=str(run_dir),
        output_path=plan_output,
    )
    ctx_path = run_dir / "03-plan" / "prompt-context.md"
    ctx_path.write_text(ctx, encoding="utf-8")
    return ctx_path


# =====================================================================
# 子命令: replay (任务 3)
# =====================================================================


def cmd_replay(args: argparse.Namespace) -> int:
    """recorded mode: parse -> 拷 fixture -> validate -> render, 无暂停."""
    input_path = args.input
    fixture_dir = Path(args.fixture)
    theme = args.theme
    preset = args.preset

    input_p = Path(input_path)
    if not input_p.exists():
        print(f"ERROR: input path not found: {input_path}", file=sys.stderr)
        return EXIT_USAGE

    output_path = args.output or str(Path(input_path).parent / "output" / "deck.pptx")
    # run 目录建在 output 旁的 .ppt-workdir
    output_root = Path(output_path).parent
    run_dir = _new_run_dir(output_root)

    input_kind = "file" if input_p.is_file() else "dir"
    manifest = _init_manifest(
        run_dir,
        mode="replay",
        input_path=str(input_p),
        input_sha256=_sha256_input(input_p),
        input_kind=input_kind,
        preset=preset,
        theme=theme,
        output_path=str(output_path),
        taste_requested=bool(getattr(args, "with_taste", False)),
    )

    # 1. parse (D6: 重跑 parse 做 E2E 覆盖, 但输出不喂下游)
    _stage_start(run_dir, manifest, "parse")
    try:
        _run_parse(run_dir, str(input_p))
    except SystemExit as e:
        _stage_failed(run_dir, manifest, "parse")
        _write_error(
            run_dir, stage="parse", slide_no=None, rule="parse.failed",
            message=f"parse 退出码 {e.code}", remediation="检查 input 路径与 markdown 结构",
        )
        return EXIT_FAIL
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "parse")
        _write_error(
            run_dir, stage="parse", slide_no=None, rule="parse.error",
            message=str(e), remediation="检查 input 路径与 markdown 结构",
        )
        return EXIT_FAIL
    _stage_done(run_dir, manifest, "parse")

    # 2. architect: 拷 fixture recorded/architect-output.yaml -> 02-architect/output.yaml
    _stage_start(run_dir, manifest, "architect")
    arch_src = fixture_dir / "recorded" / "architect-output.yaml"
    if not arch_src.exists():
        _stage_failed(run_dir, manifest, "architect")
        _write_error(
            run_dir, stage="architect", slide_no=None, rule="fixture.missing",
            message=f"fixture 缺 {arch_src}", remediation="检查 --fixture 目录结构",
        )
        return EXIT_FAIL
    arch_out = run_dir / "02-architect" / "output.yaml"
    shutil.copyfile(arch_src, arch_out)
    import yaml  # noqa: PLC0415

    # L2: fixture yaml 解析加防护 (与 resume 协议层 invalid_yaml 对称, 防非法 fixture 崩进程)
    try:
        arch = yaml.safe_load(arch_out.read_text(encoding="utf-8"))
        if not isinstance(arch, dict):
            raise ValueError("architect fixture YAML 顶层不是 mapping")
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "architect")
        _write_error(
            run_dir, stage="architect", slide_no=None, rule="fixture.invalid_yaml",
            message=f"fixture recorded/architect-output.yaml 非法 YAML: {e}",
            remediation="检查 --fixture 目录 recorded/architect-output.yaml 语法",
        )
        return EXIT_FAIL
    # replay 写 validation.json 但不据 architect issues fail (D6: plan 阶段 validate_plan 才是硬门)
    _validate_architecture_to_json(run_dir, arch, preset)
    _stage_done(run_dir, manifest, "architect")

    # 3. plan: assemble theme-prompt + 拷 fixture recorded/plan-output.yaml
    _stage_start(run_dir, manifest, "plan")
    _assemble_theme_prompt(run_dir, theme)
    plan_src = fixture_dir / "recorded" / "plan-output.yaml"
    if not plan_src.exists():
        _stage_failed(run_dir, manifest, "plan")
        _write_error(
            run_dir, stage="plan", slide_no=None, rule="fixture.missing",
            message=f"fixture 缺 {plan_src}", remediation="检查 --fixture 目录结构",
        )
        return EXIT_FAIL
    plan_out = run_dir / "03-plan" / "output.yaml"
    shutil.copyfile(plan_src, plan_out)
    # replay taste: 若请求, 传 fixture recorded/taste-report.json 给 plan gate 末尾确定性回放
    taste_fix = (
        fixture_dir / "recorded" / "taste-report.json"
        if manifest.get("taste_requested")
        else None
    )
    rc = _resume_plan_gate(
        run_dir, manifest, plan_out, theme, str(output_path), taste_fixture=taste_fix
    )
    return rc


# =====================================================================
# 子命令: run (任务 5)
# =====================================================================


def cmd_run(args: argparse.Namespace) -> int:
    """会话桥接 mode: parse -> 写 architect prompt-context -> exit 3."""
    input_path = args.input
    theme = args.theme
    preset = args.preset

    input_p = Path(input_path)
    if not input_p.exists():
        print(f"ERROR: input path not found: {input_path}", file=sys.stderr)
        return EXIT_USAGE

    output_path = args.output or str(Path(input_path).parent / "output" / "deck.pptx")
    output_root = Path(output_path).parent
    run_dir = _new_run_dir(output_root)

    input_kind = "file" if input_p.is_file() else "dir"
    taste_requested = bool(getattr(args, "with_taste", False))
    manifest = _init_manifest(
        run_dir,
        mode="bridge",
        input_path=str(input_p),
        input_sha256=_sha256_input(input_p),
        input_kind=input_kind,
        preset=preset,
        theme=theme,
        output_path=str(output_path),
        taste_requested=taste_requested,
    )

    # parse
    _stage_start(run_dir, manifest, "parse")
    try:
        parsed_json = _run_parse(run_dir, str(input_p))
    except SystemExit as e:
        _stage_failed(run_dir, manifest, "parse")
        _write_error(
            run_dir, stage="parse", slide_no=None, rule="parse.failed",
            message=f"parse 退出码 {e.code}", remediation="检查 input 路径与 markdown 结构",
        )
        return EXIT_FAIL
    _stage_done(run_dir, manifest, "parse")

    # 写 architect prompt-context
    arch_output = str(run_dir / "02-architect" / "output.yaml")
    _write_architect_prompt_context(run_dir, parsed_json, preset, arch_output)

    # state: 等会话产出 architect output.yaml
    _write_state(
        run_dir,
        current_stage="architect",
        awaiting="02-architect/output.yaml",
        mode="bridge",
        next_action="resume",
        expected_schema="content-architecture",
    )

    if taste_requested:
        print("[orchestrator] taste 已请求 (--with-taste): 将在 render 完成后作为可选末阶段触发 (05-taste/)")

    print(f"[orchestrator] run 目录: {run_dir}")
    print(f"[orchestrator] NEED_LLM: 会话请按 02-architect/prompt-context.md 产出 {arch_output}")
    print(f"[orchestrator] 产出后: uv run --script {PLUGIN_ROOT}/engine/orchestrator.py resume {run_dir}")
    return EXIT_NEED_LLM


# =====================================================================
# 子命令: resume (任务 6)
# =====================================================================


def cmd_resume(args: argparse.Namespace) -> int:
    """推进会话桥接: 校验 awaiting -> 推进 (exit 3) 或终点 (exit 0) 或失败 (exit 1)."""
    run_dir = Path(args.run_dir)
    if not (run_dir / "state.json").exists():
        print(f"ERROR: 非法 run 目录 (缺 state.json): {run_dir}", file=sys.stderr)
        return EXIT_USAGE

    state = _read_state(run_dir)
    manifest = _read_manifest(run_dir)
    current_stage = state.get("current_stage")
    theme = manifest.get("theme", "huawei")
    preset = manifest.get("preset", "research-report")
    output_path = manifest.get("output_path")

    if current_stage == "architect":
        return _resume_architect_gate(run_dir, manifest, preset, theme)
    if current_stage == "plan":
        plan_out = run_dir / "03-plan" / "output.yaml"
        return _resume_plan_gate(run_dir, manifest, plan_out, theme, output_path)
    if current_stage == "taste":
        return _resume_taste_gate(run_dir, manifest)
    if current_stage == "done":
        print("[orchestrator] 该 run 已完成 (current_stage=done)")
        return EXIT_OK
    print(f"ERROR: 未知 current_stage: {current_stage}", file=sys.stderr)
    return EXIT_USAGE


def _resume_architect_gate(run_dir: Path, manifest: dict, preset: str, theme: str) -> int:
    """architect gate: 读 02-architect/output.yaml -> validate_architecture -> 推进到 plan.

    两层语义 (team-lead 2026-06-11 裁决):
    1. 协议层硬门: output.yaml 缺失/空/非法 YAML -> error.json (rule=protocol.*) + exit 1.
    2. validate_architecture 内容质量 issues 降级 advisory: 写 validation.json 但不 fail,
       继续 exit 3 推进 (依据: v3.4.0 SKILL.md Stage 2 从不调该校验, 硬 fail 构成行为回归;
       与 replay 路径语义对称 — replay 同样只写 validation.json 不据 architect issues fail).
    """
    import yaml  # noqa: PLC0415

    # --- 协议层硬门 (缺失/空/非法 YAML) ---
    arch_out = run_dir / "02-architect" / "output.yaml"
    if not arch_out.exists():
        _stage_failed(run_dir, manifest, "architect")
        _write_error(
            run_dir, stage="architect", slide_no=None, rule="protocol.missing_output",
            message=f"会话未产出 02-architect/output.yaml (architecture output.yaml 缺失): {arch_out}",
            remediation="按 02-architect/prompt-context.md 产出 output.yaml 后再 resume",
        )
        return EXIT_FAIL

    raw = arch_out.read_text(encoding="utf-8").strip()
    if not raw:
        _stage_failed(run_dir, manifest, "architect")
        _write_error(
            run_dir, stage="architect", slide_no=None, rule="protocol.empty",
            message=f"02-architect/output.yaml 为空: {arch_out}",
            remediation="按模板产出非空 architecture 后 resume",
        )
        return EXIT_FAIL
    try:
        arch = yaml.safe_load(raw)
        if not isinstance(arch, dict):
            raise ValueError("architecture YAML 顶层不是 mapping")
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "architect")
        _write_error(
            run_dir, stage="architect", slide_no=None, rule="protocol.invalid_yaml",
            message=f"02-architect/output.yaml 非法 YAML: {e}",
            remediation="修复 YAML 语法后 resume",
        )
        return EXIT_FAIL

    # --- 内容质量层 (advisory): validate_architecture issues 写 validation.json 但不 fail ---
    _stage_start(run_dir, manifest, "architect")
    _validate_architecture_to_json(run_dir, arch, preset)  # advisory: issues 仅记录, 不 fail
    _stage_done(run_dir, manifest, "architect")

    # 推进到 plan: assemble theme-prompt + 写 plan prompt-context
    theme_prompt_path = _assemble_theme_prompt(run_dir, theme)
    plan_output = str(run_dir / "03-plan" / "output.yaml")
    _write_plan_prompt_context(run_dir, arch, theme, theme_prompt_path, plan_output)
    _write_state(
        run_dir,
        current_stage="plan",
        awaiting="03-plan/output.yaml",
        mode="bridge",
        next_action="resume",
        expected_schema="slide-plan",
    )
    print(f"[orchestrator] architect gate 通过. 会话请按 03-plan/prompt-context.md + theme-prompt.md 产出 {plan_output}")
    print(f"[orchestrator] 产出后: uv run --script {PLUGIN_ROOT}/engine/orchestrator.py resume {run_dir}")
    return EXIT_NEED_LLM


def _resume_plan_gate(
    run_dir: Path, manifest: dict, plan_out: Path, theme: str, output_path: str,
    taste_fixture: Path | None = None,
) -> int:
    """plan gate: SlidePlan.from_yaml -> validate_plan -> render -> (可选 taste) -> exit 0; 失败 exit 1.

    顶层统一 exit 1 (不透传 validate_plan 内部 1/2), error.json.rule 区分具体规则 (TC-A6).

    taste 可选末阶段 (S3-P1 档位 B): render 完成后, 若 manifest.taste_requested 为真:
    - bridge mode (taste_fixture=None): 转 taste gate (exit 3 NEED_LLM), 等会话用 ppt:taste
      产出 05-taste/taste-report.json 后 resume 校验 -> done. (LLM 评分留会话层, orchestrator
      只做 JSON 契约校验 + 归档, 接缝同 architect/plan gate.)
    - replay mode (taste_fixture 给定): 确定性回放 — 拷 fixture taste-report.json 校验后 done;
      无 fixture 则优雅跳过 (CI 无 LLM 不能真做视觉评审).
    """
    from schemas.slide_plan import SlidePlan  # noqa: PLC0415

    # --- 协议层硬门 (缺失/空) ---
    if not plan_out.exists():
        _stage_failed(run_dir, manifest, "plan")
        _write_error(
            run_dir, stage="plan", slide_no=None, rule="protocol.missing_output",
            message=f"会话未产出 03-plan/output.yaml (slide-plan output.yaml 缺失): {plan_out}",
            remediation="按 03-plan/prompt-context.md 产出 output.yaml 后再 resume",
        )
        return EXIT_FAIL

    raw = plan_out.read_text(encoding="utf-8").strip()
    if not raw:
        _stage_failed(run_dir, manifest, "plan")
        _write_error(
            run_dir, stage="plan", slide_no=None, rule="protocol.empty",
            message=f"03-plan/output.yaml 为空: {plan_out}",
            remediation="按模板产出非空 slide-plan 后 resume",
        )
        return EXIT_FAIL

    _stage_start(run_dir, manifest, "plan")
    # 1. pydantic schema 校验 (协议层: 数据契约不合法直接 fail)
    try:
        SlidePlan.from_yaml(str(plan_out))
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "plan")
        _write_error(
            run_dir, stage="plan", slide_no=None, rule="schema.variant_validation",
            message=f"slide-plan schema 校验失败: {e}",
            remediation="按 theme-prompt.md path X 修正 variant 字段后覆写 output.yaml 再 resume",
        )
        return EXIT_FAIL

    # 2. validate_plan: 内容量 + 应用率门禁
    report = _validate_plan_to_json(run_dir, plan_out)

    # 2a. 内容量 FAIL
    if not report.ok:
        first_fail = next((r for r in report.results if r.status == "FAIL"), None)
        slide_no = first_fail.slide_id if first_fail else None
        if first_fail and first_fail.point_issues:
            p = first_fail.point_issues[0]
            msg = (
                f"slide {first_fail.slide_id} ({first_fail.visual_type}): "
                f"point {p.index} = {p.char_count} chars (min {p.min_required})"
            )
        elif first_fail and first_fail.total_issue:
            msg = first_fail.total_issue
        else:
            msg = f"{report.failed} slides 内容量不达标"
        _stage_failed(run_dir, manifest, "plan")
        _write_error(
            run_dir, stage="plan", slide_no=slide_no, rule="content_volume.body_min",
            message=msg,
            remediation="从 02-architect/output.yaml source_refs 回溯源材料补充 body, 覆写 output.yaml 后 resume",
        )
        return EXIT_FAIL

    # 2b. 应用率 FAIL
    warn_below, fail_below = _load_theme_thresholds(theme)
    app_status = report.theme_application_status(warn_below, fail_below)
    if app_status == "FAIL":
        _stage_failed(run_dir, manifest, "plan")
        _write_error(
            run_dir, stage="plan", slide_no=None, rule="application_rate.fail_below_30",
            message=(
                f"huawei 18 版式应用率 {report.huawei_variant_ratio:.2%} "
                f"低于阈值 {fail_below:.0%} (count={report.huawei_variant_count}/{report.total_slides})"
            ),
            remediation="按 theme-prompt.md 重选 visual_type (cards-N -> kpi-stats/architecture-layered 等), 覆写后 resume",
        )
        return EXIT_FAIL
    _stage_done(run_dir, manifest, "plan")

    # 3. render
    _stage_start(run_dir, manifest, "render")
    try:
        deck_path = _run_render(run_dir, plan_out, theme, output_path)
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "render")
        _write_error(
            run_dir, stage="render", slide_no=None, rule="render.error",
            message=f"render 失败: {e}",
            remediation="检查 visual_type 是否有对应 renderer / theme 是否合法",
        )
        return EXIT_FAIL
    _stage_done(run_dir, manifest, "render")

    # 4. taste 可选末阶段 (S3-P1 档位 B): render 完成后接入
    if manifest.get("taste_requested"):
        if taste_fixture is not None:
            # replay: 确定性回放, 拷 fixture 校验后落到 done (失败 exit 1, 优雅跳过 exit 0)
            rc = _replay_taste(run_dir, manifest, taste_fixture)
            if rc != EXIT_OK:
                return rc
            # 成功 / 优雅跳过 -> 继续走 done
        else:
            # bridge: 转 taste gate, done 推迟到 taste resume (exit 3 NEED_LLM)
            return _enter_taste_gate(run_dir, manifest, deck_path, report.total_slides)

    # state: done
    _write_state(
        run_dir,
        current_stage="done",
        awaiting=None,
        mode=manifest.get("mode", "bridge"),
        next_action="done",
        expected_schema=None,
    )
    print(f"[orchestrator] 完成. deck: {output_path} ({report.total_slides} slides)")
    print(f"[orchestrator] run 目录: {run_dir}")
    return EXIT_OK


# =====================================================================
# taste gate (任务: S3-P1 档位 B 可选末阶段)
# =====================================================================


def _enter_taste_gate(run_dir: Path, manifest: dict, deck_path: Path, total_slides: int) -> int:
    """bridge mode: render 完成后转 taste gate. 写 prompt-context + state, exit 3 NEED_LLM.

    LLM 视觉评分留会话层 (orchestrator 零 LLM 逻辑): 会话用 ppt:taste 评审 deck,
    把结构化 JSON 落 05-taste/taste-report.json, 再 resume 由 orchestrator 校验契约.
    """
    _ensure_taste_stage(manifest)
    _stage_start(run_dir, manifest, "taste")

    taste_json = run_dir / "05-taste" / "taste-report.json"
    ctx = _TASTE_PROMPT_TEMPLATE.format(
        deck_path=str(deck_path),
        taste_json_path=str(taste_json),
        plugin_root=str(PLUGIN_ROOT),
        run_dir=str(run_dir),
        total_slides=total_slides,
    )
    (run_dir / "05-taste" / "prompt-context.md").write_text(ctx, encoding="utf-8")

    _write_state(
        run_dir,
        current_stage="taste",
        awaiting="05-taste/taste-report.json",
        mode=manifest.get("mode", "bridge"),
        next_action="resume",
        expected_schema="taste-report",
    )
    print(f"[orchestrator] render 完成, deck: {deck_path}")
    print(f"[orchestrator] NEED_LLM (taste): 会话请按 05-taste/prompt-context.md 用 ppt:taste 产出 {taste_json}")
    print(f"[orchestrator] 产出后: uv run --script {PLUGIN_ROOT}/engine/orchestrator.py resume {run_dir}")
    return EXIT_NEED_LLM


def _resume_taste_gate(run_dir: Path, manifest: dict) -> int:
    """taste gate: 校验 05-taste/taste-report.json 符合 TasteReport 契约 -> done; 失败 exit 1.

    两层语义同 architect/plan gate:
    1. 协议层硬门: JSON 缺失/空/非法 JSON -> error.json (rule=protocol.*) + exit 1.
    2. schema 层: 不符合 TasteReport (内部一致性护栏失败等) -> error.json (rule=schema.taste_report) + exit 1.
    deck 已渲染完成 (在 output / 04-render/deck.pptx), taste 失败不丢 deck — 修 JSON 后再 resume 即可.
    """
    taste_json = run_dir / "05-taste" / "taste-report.json"
    _ensure_taste_stage(manifest)

    # --- 协议层硬门 (缺失/空/非法 JSON) ---
    if not taste_json.exists():
        _stage_failed(run_dir, manifest, "taste")
        _write_error(
            run_dir, stage="taste", slide_no=None, rule="protocol.missing_output",
            message=f"会话未产出 05-taste/taste-report.json: {taste_json}",
            remediation="按 05-taste/prompt-context.md 用 ppt:taste 产出 taste-report.json 后再 resume",
        )
        return EXIT_FAIL

    raw = taste_json.read_text(encoding="utf-8").strip()
    if not raw:
        _stage_failed(run_dir, manifest, "taste")
        _write_error(
            run_dir, stage="taste", slide_no=None, rule="protocol.empty",
            message=f"05-taste/taste-report.json 为空: {taste_json}",
            remediation="按 schemas/taste_report.py 契约产出非空 JSON 后 resume",
        )
        return EXIT_FAIL
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        _stage_failed(run_dir, manifest, "taste")
        _write_error(
            run_dir, stage="taste", slide_no=None, rule="protocol.invalid_json",
            message=f"05-taste/taste-report.json 非法 JSON: {e}",
            remediation="修复 JSON 语法后 resume",
        )
        return EXIT_FAIL

    # --- schema 层 (TasteReport 契约 + 内部一致性护栏) ---
    _stage_start(run_dir, manifest, "taste")
    try:
        from schemas.taste_report import validate_taste_report_file  # noqa: PLC0415

        report = validate_taste_report_file(str(taste_json))
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "taste")
        _write_error(
            run_dir, stage="taste", slide_no=None, rule="schema.taste_report",
            message=f"taste-report.json 不符合 TasteReport schema: {e}",
            remediation="按 schemas/taste_report.py 的 6 条硬约束修正 JSON (Step 4c 自校验 OK) 后 resume",
        )
        return EXIT_FAIL

    _record_taste_result(run_dir, manifest, report)
    _stage_done(run_dir, manifest, "taste")
    _write_state(
        run_dir,
        current_stage="done",
        awaiting=None,
        mode=manifest.get("mode", "bridge"),
        next_action="done",
        expected_schema=None,
    )
    print(
        f"[orchestrator] taste 完成. layout_avg={report.summary.layout_avg} "
        f"palette_avg={report.summary.palette_avg} (AP 命中 {len(report.antipattern_hits)} 处). "
        f"报告: {taste_json}"
    )
    return EXIT_OK


def _replay_taste(run_dir: Path, manifest: dict, taste_fixture: Path) -> int:
    """replay mode: 确定性回放 taste. 拷 fixture taste-report.json -> 05-taste/ -> 校验.

    replay 是 CI 0-LLM 路径, 无法真做视觉评审:
    - fixture 有 recorded/taste-report.json: 拷入 + 校验契约 + 落 manifest.taste_result (exit 0); 不合规 exit 1.
    - fixture 无: 优雅跳过 (打 notice, exit 0) — 不强制 CI 提供 taste fixture.
    """
    taste_json = run_dir / "05-taste" / "taste-report.json"
    if not taste_fixture.exists():
        print(
            "[orchestrator] replay --with-taste: fixture 无 recorded/taste-report.json, "
            "跳过 taste (CI 无 LLM 不能真做视觉评审, 优雅降级)",
            file=sys.stderr,
        )
        return EXIT_OK

    _ensure_taste_stage(manifest)
    _stage_start(run_dir, manifest, "taste")
    shutil.copyfile(taste_fixture, taste_json)
    try:
        from schemas.taste_report import validate_taste_report_file  # noqa: PLC0415

        report = validate_taste_report_file(str(taste_json))
    except Exception as e:  # noqa: BLE001
        _stage_failed(run_dir, manifest, "taste")
        _write_error(
            run_dir, stage="taste", slide_no=None, rule="fixture.invalid_taste_report",
            message=f"fixture recorded/taste-report.json 不符合 TasteReport schema: {e}",
            remediation="检查 --fixture 目录 recorded/taste-report.json 结构",
        )
        return EXIT_FAIL

    _record_taste_result(run_dir, manifest, report)
    _stage_done(run_dir, manifest, "taste")
    print(
        f"[orchestrator] replay taste 回放完成. layout_avg={report.summary.layout_avg} "
        f"palette_avg={report.summary.palette_avg}. 报告: {taste_json}"
    )
    return EXIT_OK


# =====================================================================
# CLI
# =====================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="ppt 产线短命状态机 (run / resume / replay)",
    )
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="会话桥接 mode: parse 后在 architect gate 暂停 (exit 3)")
    run_cmd.add_argument("input", help="输入路径 (目录或文件)")
    run_cmd.add_argument("--preset", default="research-report")
    run_cmd.add_argument("--theme", default="huawei")
    run_cmd.add_argument("--output", default=None, help="输出 pptx 路径")
    run_cmd.add_argument("--with-taste", action="store_true", dest="with_taste")

    resume_cmd = sub.add_parser("resume", help="推进会话桥接: 校验 awaiting 后推进或失败")
    resume_cmd.add_argument("run_dir", help="run 目录路径")

    replay_cmd = sub.add_parser("replay", help="recorded mode: 固定 fixture 回放, 无暂停")
    replay_cmd.add_argument("input", help="输入路径 (目录或文件)")
    replay_cmd.add_argument("--fixture", required=True, help="fixture 目录 (含 recorded/)")
    replay_cmd.add_argument("--preset", default="research-report")
    replay_cmd.add_argument("--theme", default="huawei")
    replay_cmd.add_argument("--output", default=None, help="输出 pptx 路径")
    replay_cmd.add_argument("--with-taste", action="store_true", dest="with_taste")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_usage(sys.stderr)
        print("ERROR: 需要子命令 (run / resume / replay)", file=sys.stderr)
        return EXIT_USAGE

    if args.command == "run":
        return cmd_run(args)
    if args.command == "resume":
        return cmd_resume(args)
    if args.command == "replay":
        return cmd_replay(args)
    return EXIT_USAGE


# =====================================================================
# Prompt 模板 (plan §LLM Prompt 完整模板; 文本来源 = skills/create/SKILL.md +
# design-guide.md + preset YAML, 不发明新 prompt)
# =====================================================================

_ARCHITECT_PROMPT_TEMPLATE = """# Stage 2: 内容架构设计 (orchestrator 桥接上下文)

> 本文件由 orchestrator 在 parse 完成后生成. 你 (会话 Claude) 作为**内容架构师**, 读完本文件后产出 `{output_path}`, 然后由用户确认 gate, 再 resume.

## 输入材料摘要 (来自 01-parse/parsed-content.json)

{parsed_content_summary}

完整 parsed 内容见同 run 目录 `01-parse/parsed-content.json` (如需逐块细节请 Read 它).

## 预设: {preset_name}

**结构要求 (required_sections)**:
{preset_structure}

**内容规则**:
{preset_content_rules}

## 设计知识库 (design-guide.md)

{design_guide_text}

## 你的任务

作为内容架构师:
1. 全局分析输入材料的核心信息, 提炼核心论点 / 叙事线
2. 做内容取舍 (哪些纳入 / 裁剪), 划分章节, 设计叙事弧线
3. 为每页规划结构化内容要点 (每 point 的 body **80-150 字**, 含数据 / 案例 / 论证细节)
4. 为每页撰写 description (1-3 句上下文), 数据引用页标 footnote

## 内容量硬约束 (Stage 3 的 validate_plan 会再次拦截, 此处先尽力保证)

- content_points.body 字段 80-150 字
- cards / comparison / process 类型 content_points **必须有 heading**
- data-contrast **必须有 metric_value + metric_label**
- 非豁免页面 (hero-statement / quote-hero / story-card 除外) **必须有 description**
- 有数据引用的页面 **必须有 footnote**

## 产出格式 (写到 {output_path})

```yaml
thesis: "核心论点 (完整句子)"
target_audience: "目标受众"
arc: "opening -> context -> evidence -> ... -> closing"
chapters:
  - title: "章节名"
    key_message: "核心信息"
    source_refs: ["file.md:15-42"]
    slide_briefs:
      - slide_title: "行动标题 (传达观点, 不只是描述)"
        visual_type_hint: "data-contrast"
        description: "1-3 句上下文 (必填, 豁免类型除外)"
        content_points:
          - heading: "卡片标题"
            body: "80-150 字详细阐述, 从源材料提取数据 / 案例 / 论证"
            metric_value: "大号指标值"
            metric_label: "指标标签"
        footnote: "数据来源 (有数据引用时必填)"
total_slides: 18
excluded_content:
  - reason: "裁剪原因"
    source_ref: "file.md:120-135"
    content_summary: "被裁剪的内容摘要"
```

## 完成协议 (会话桥接)

1. 写完 `{output_path}`
2. 输出架构摘要 (核心论点、章节标题 + 核心信息、预计页数、被裁剪内容清单)
3. **AskUserQuestion 确认 gate** (保留, 不可跳):
   - 选项 1: "确认, 进入视觉规划" -> 用户选此后执行 resume
   - 选项 2: "需要调整" (用户输入修改意见后重做 Architect, 覆写 output.yaml)
   - 选项 3: "查看某章节的详细 content_points"
4. 用户确认后: `uv run --script {plugin_root}/engine/orchestrator.py resume {run_dir}`
"""


_PLAN_PROMPT_TEMPLATE = """# Stage 3: 视觉规划 (orchestrator 桥接上下文)

> 本文件由 orchestrator 在 architect gate 通过后生成. 你 (会话 Claude) 作为**视觉规划师**, 读完本文件 + `{theme_prompt_path}` 后产出 `{output_path}`, 然后 resume.

## 内容架构摘要 (来自 02-architect/output.yaml)

{architecture_summary}

完整架构见同 run 目录 `02-architect/output.yaml`.

## 主题决策框架 (强制 Read)

**先 Read `{theme_prompt_path}`** — 由 engine/prompt_assembler.py 从 themes/{theme_name}/preferences.yaml + schemas/variants.py 派生, 含 6 类硬约束 + 12 类软引导 + 18 版式字段速查 + 退回链 + path X 字段填法.

**所有视觉规划决策必须严格遵循 `{theme_prompt_path}`**.

## 你的任务 (视觉规划师)

为每页:
1. 按 theme-prompt.md 硬约束 + 软引导选 visual_type (通用 fallback 决策树仅在 theme-prompt 加载失败时用)
2. key_points 用结构化对象格式 (heading + body, data-contrast 加 metric_value + metric_label)
3. 每页有 description (豁免类型除外), 数据页有 footnote
4. 连续 2 页不得用相同 visual_type (布局多样性)

## huawei 18 版式字段填法 (path X)

- 公共字段 (title / subtitle / description) -> `slide.content`
- 专属字段 (kpis / chapters / layers / steps / phases / quadrants / personas / risks / units / ...) -> `slide.variant`
- 不要把专属字段平铺到 slide.content 顶层

## 通用 Visual Type 决策树 (仅 theme-prompt.md 加载失败时)

1. 有序列 / 流程 -> process-N-phase (N=2-5)
2. 有对比 -> comparison-N (N=2-5)
3. 有并列非序列条目 -> cards-N (N=2-6)
4. 两组数据张力 -> data-contrast
5. 有力引言 -> quote-hero
6. 数据是表格 -> table
7. 单句核心陈述 -> hero-statement
8. 默认 -> bullets

通用禁止: hero-statement 不得用于 3+ 条目; table 不得用于流程; bullets 不得用于并列对比.

## 产出 (写到 {output_path})

slide-plan.yaml, schema 由 schemas/slide_plan.py 定义 (顶层 meta + narrative + slides[]).

## 完成协议 (会话桥接)

1. 写完 `{output_path}`
2. `uv run --script {plugin_root}/engine/orchestrator.py resume {run_dir}`
3. orchestrator resume 时: (1) SlidePlan.from_yaml(output.yaml) pydantic 校验 (2) validate_plan(output.yaml) 内容量 + 应用率门禁 (3) 通过则 render -> exit 0; 失败写 error.json:
   - 内容量 FAIL (exit 1, rule=content_volume.*): 读 error.json 的 message, 从 architecture source_refs 回溯源材料补充 body, 覆写 output.yaml 后再 resume. **连续 3 轮无法通过 -> AskUserQuestion 让用户决策**
   - 应用率 FAIL (exit 1, rule=application_rate.fail_below_30): 按 theme-prompt.md 重选 visual_type (cards-N -> kpi-stats / architecture-layered 等). **连续 2 轮未达阈值 -> AskUserQuestion**
"""


_TASTE_PROMPT_TEMPLATE = """# Stage 5 (可选): 视觉评审 taste (orchestrator 桥接上下文)

> 本文件由 orchestrator 在 render 完成后生成 (run 时传了 --with-taste). 你 (会话 Claude) 用 **ppt:taste** skill 对已渲染的 deck 做视觉评审, 把结构化 JSON 落到指定路径后 resume.

## 已渲染产物

- deck (pptx): `{deck_path}` (共 {total_slides} 页, 已渲染完成)
- 评审报告 JSON 落点 (**orchestrator 等待此文件**): `{taste_json_path}`

## 你的任务

1. 调用 **ppt:taste** skill 评审 `{deck_path}` (双轴评分 layout / palette 解耦, 逐页 + deck 级).
2. 把结构化 JSON 产出**落到 `{taste_json_path}`** (ppt:taste 默认落在 deck 同目录, 评审后请确保 JSON 在该路径; 可直接 Write 或 copy 过去).
3. JSON 字段契约**单一来源**: `{plugin_root}/schemas/taste_report.py` (pydantic TasteReport). 写完用 Step 4c 自校验:
   `uv run --script {plugin_root}/schemas/taste_report.py {taste_json_path}`
   输出 `OK:` 才算合格; `FAIL:` 则按报错修正重写 (不要把不合规 JSON 留给 resume).

## 完成协议 (会话桥接)

1. 写完并自校验 `{taste_json_path}` (Step 4c 输出 OK)
2. `uv run --script {plugin_root}/engine/orchestrator.py resume {run_dir}`
3. orchestrator resume 校验该 JSON 符合 TasteReport 契约 -> 通过则 state=done (exit 0) + manifest.taste_result 记双轴均分 + AP 计数; 不合规写 error.json (stage=taste, rule=protocol.* / schema.taste_report) + exit 1, 按 message 修正后再 resume.

## 说明

taste 是**可选末阶段**: deck 已渲染完成 (在 `{deck_path}` 与最终 output). taste 评分是质量参考, **不影响 deck 本身** — 即使分数低, deck 仍可用. taste 失败 (JSON 不合规) 也不丢 deck, 修 JSON 重 resume 即可.
"""


if __name__ == "__main__":
    sys.exit(main())
