# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""华为主题 tokens / layouts 强约束对账模块（PRD §11 + §6.3/6.4）。

提供可导入的断言 API 与 CLI 入口：

1. `assert_tokens_match(tokens_path, layouts_path, expected=None) -> list[dict]`
   读两份 yaml，对照 expected（默认使用本模块 EXPECTED_* 常量），按分级 tolerance 检查。
   返回差异列表（每条含 kind / group / key / expected / actual / tolerance）。

2. `assert_theme_dir_match(theme_dir, tolerance_overrides=None) -> list[dict]`
   便捷 API：接受主题根目录自动解析 tokens.yaml + layouts.yaml。

3. CLI: `python tests/pixel/assert_tokens_match.py <tokens.yaml> [layouts.yaml]`
   或 `python tests/pixel/assert_tokens_match.py <theme_dir>`

分级 tolerance（team-lead 规范）：
- **colors**: 0（严格等于，像素级色值）
- **type_scale**: ±1 px
- **layout 常规**: ±2 px
- **大数字**（section-divider 360 / kpi 96 / cover 108 / thankyou 360）: ±5 px

差异超 tolerance 即记录为命中。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


# ==================== EXPECTED_* 常量（PRD §6.3 / §6.4 / §11） ====================


EXPECTED_COLORS: dict[str, str] = {
    "primary": "#C7000B",
    "primary_dark": "#8A0008",
    "primary_soft": "#FDECEE",
    "ink": "#1F1F1F",
    "ink_soft": "#4B4B4B",
    "ink_mute": "#9A9A9A",
    "ink_dark": "#2A2A2A",
    "rule": "#D9D9D9",
    "rule_soft": "#ECECEC",
    "paper": "#FFFFFF",
    "paper_2": "#F4F4F4",
    "paper_3": "#EAEAEA",
    "accent": "#D97706",
}


EXPECTED_TYPE_SCALE: dict[str, int] = {
    "cover": 108,
    "section": 84,
    "title": 54,
    "subtitle": 36,
    "h4": 28,
    "body": 24,
    "small": 20,
    "micro": 16,
    "nano": 14,
}


EXPECTED_FONTS_SANS: list[str] = ["Inter", "Noto Sans SC", "Microsoft YaHei"]
EXPECTED_FONTS_MONO: list[str] = ["JetBrains Mono"]


EXPECTED_CANVAS: dict[str, int] = {
    "width_px": 1920,
    "height_px": 1080,
    "padding_top_px": 88,
    "padding_left_px": 96,
    "padding_right_px": 96,
    "padding_bottom_px": 76,
}


# PRD §11 强约束版式参数 + Plan §O6 权威字号表
EXPECTED_LAYOUT_STRONG: dict[tuple[str, str], Any] = {
    ("cover_left_bar", "bar_width_px"): 16,
    ("cover_left_bar", "title_size_px"): 108,
    ("cover_left_bar", "subtitle_size_px"): 34,
    ("toc", "giant_title_size_px"): 300,
    ("section_divider_dark", "big_number_size_px"): 360,
    ("section_divider_dark", "big_number_weight"): 200,
    ("section_divider_dark", "title_size_px"): 88,
    ("section_divider_dark", "background_token"): "ink_dark",
    ("matrix_2x2", "border_width_px"): 2,
    ("matrix_2x2", "border_token"): "ink",
    ("matrix_2x2", "quadrant_heading_size_px"): 22,
    ("architecture_layered", "header_column_px"): 260,
    ("architecture_layered", "cell_columns"): 6,
    ("architecture_layered", "header_name_size_px"): 24,
    ("kpi_stats", "value_size_px"): 108,  # §O6 修正：HTML 实测 108（原 96 错）
    ("kpi_stats", "label_size_px"): 18,
    ("kpi_stats", "trend_size_px"): 14,
    ("thankyou", "title_size_px"): 360,
}


# 大数字字段（tolerance ±5）
BIG_NUMBER_KEYS: set[tuple[str, str]] = {
    ("section_divider_dark", "big_number_size_px"),
    ("kpi_stats", "value_size_px"),
    ("cover_left_bar", "title_size_px"),
    ("thankyou", "title_size_px"),
    ("toc", "giant_title_size_px"),
}


REQUIRED_LAYOUT_GROUPS: set[str] = {
    "cover_left_bar", "toc", "section_divider_dark", "kpi_stats",
    "matrix_2x2", "architecture_layered", "timeline_huawei", "process_flow_huawei",
    "swot", "roadmap", "pyramid", "heatmap_matrix", "thankyou",
    "cards_6", "rings", "personas",
}


# ==================== 分级 tolerance ====================


DEFAULT_TOLERANCES: dict[str, int] = {
    "color": 0,
    "type_scale": 1,
    "canvas": 2,
    "layout": 2,
    "big_number": 5,
    "enum": 0,  # 字符串枚举（如 background_token: "ink_dark"）严格匹配
}


# ==================== 内部工具 ====================


def _diff(
    kind: str,
    group: str,
    key: str,
    expected: Any,
    actual: Any,
    tolerance: int | None = None,
) -> dict:
    return {
        "kind": kind,
        "group": group,
        "key": key,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
    }


def _check_int_with_tol(expected: int, actual: Any, tol: int) -> bool:
    """整数值，允许 ±tol 范围。"""
    if not isinstance(actual, int):
        return False
    return abs(expected - actual) <= tol


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


# ==================== 对账核心 ====================


def _build_expected_bundle() -> dict:
    """构造默认的 expected 结构（供调用方覆盖）。"""
    return {
        "colors": dict(EXPECTED_COLORS),
        "type_scale_px": dict(EXPECTED_TYPE_SCALE),
        "fonts": {"sans": list(EXPECTED_FONTS_SANS), "mono": list(EXPECTED_FONTS_MONO)},
        "canvas": dict(EXPECTED_CANVAS),
        "layout_strong": dict(EXPECTED_LAYOUT_STRONG),
        "big_number_keys": set(BIG_NUMBER_KEYS),
        "required_groups": set(REQUIRED_LAYOUT_GROUPS),
    }


def assert_tokens_match(
    tokens_path: str | Path,
    layouts_path: str | Path,
    expected: dict | None = None,
    tolerances: dict[str, int] | None = None,
) -> list[dict]:
    """核心断言 API：读两份 yaml 对账 expected。

    Args:
        tokens_path: tokens.yaml 路径
        layouts_path: layouts.yaml 路径
        expected: 期望结构（默认由 _build_expected_bundle() 生成，含所有 EXPECTED_*）
        tolerances: 分级容差覆盖，缺省使用 DEFAULT_TOLERANCES

    Returns:
        差异列表；空列表表示全部通过。
    """
    tokens_path = Path(tokens_path)
    layouts_path = Path(layouts_path)

    diffs: list[dict] = []

    if not tokens_path.is_file():
        diffs.append(_diff("missing_file", "tokens.yaml", "", None, str(tokens_path)))
        return diffs
    if not layouts_path.is_file():
        diffs.append(_diff("missing_file", "layouts.yaml", "", None, str(layouts_path)))
        return diffs

    tokens = _load_yaml(tokens_path)
    layouts = _load_yaml(layouts_path)

    exp = expected if expected is not None else _build_expected_bundle()
    tol = {**DEFAULT_TOLERANCES, **(tolerances or {})}

    # 1. colors（tolerance=0，严格等于）
    colors = tokens.get("colors", {}) or {}
    for key, expected_val in (exp.get("colors") or {}).items():
        actual = colors.get(key)
        if actual != expected_val:
            diffs.append(_diff("color", "colors", key, expected_val, actual, tol["color"]))

    # 2. type_scale_px（tolerance=±1）
    scale = tokens.get("type_scale_px", {}) or {}
    for key, expected_val in (exp.get("type_scale_px") or {}).items():
        actual = scale.get(key)
        if not _check_int_with_tol(expected_val, actual, tol["type_scale"]):
            diffs.append(
                _diff("type_scale", "type_scale_px", key, expected_val, actual, tol["type_scale"])
            )

    # 3. fonts（严格等于）
    fonts = tokens.get("fonts", {}) or {}
    fonts_exp = exp.get("fonts") or {}
    for fkey in ("sans", "mono"):
        if fkey in fonts_exp and fonts.get(fkey) != fonts_exp[fkey]:
            diffs.append(_diff("fonts", "fonts", fkey, fonts_exp[fkey], fonts.get(fkey), 0))

    # 4. canvas（tolerance=±2）
    canvas = layouts.get("canvas", {}) or {}
    for key, expected_val in (exp.get("canvas") or {}).items():
        actual = canvas.get(key)
        if not _check_int_with_tol(expected_val, actual, tol["canvas"]):
            diffs.append(_diff("canvas", "canvas", key, expected_val, actual, tol["canvas"]))

    # 5. layout strong（layout ±2，大数字 ±5，字符串枚举严格）
    big_keys = exp.get("big_number_keys") or set()
    for (group, key), expected_val in (exp.get("layout_strong") or {}).items():
        actual = (layouts.get(group) or {}).get(key)
        if isinstance(expected_val, str):
            # 枚举字段（如 background_token: 'ink_dark'）严格等
            if actual != expected_val:
                diffs.append(_diff("enum", group, key, expected_val, actual, 0))
        elif (group, key) in big_keys:
            if not _check_int_with_tol(expected_val, actual, tol["big_number"]):
                diffs.append(
                    _diff("big_number", group, key, expected_val, actual, tol["big_number"])
                )
        else:
            if not _check_int_with_tol(expected_val, actual, tol["layout"]):
                diffs.append(_diff("layout", group, key, expected_val, actual, tol["layout"]))

    # 6. required layout groups（存在性）
    required = exp.get("required_groups") or set()
    missing = required - set(layouts.keys())
    for g in sorted(missing):
        diffs.append(_diff("missing_group", g, "", "<present>", None, 0))

    return diffs


def assert_theme_dir_match(
    theme_dir: str | Path,
    tolerances: dict[str, int] | None = None,
) -> list[dict]:
    """便捷 API：接受主题根目录，自动解析 tokens.yaml + layouts.yaml。"""
    theme_dir = Path(theme_dir)
    return assert_tokens_match(
        theme_dir / "tokens.yaml",
        theme_dir / "layouts.yaml",
        expected=None,
        tolerances=tolerances,
    )


# ==================== CLI ====================


def _format_report(diffs: list[dict]) -> str:
    if not diffs:
        return "PASS: tokens/layouts 与 PRD 强约束完全一致"
    lines = [f"FAIL: {len(diffs)} 项差异"]
    for d in diffs:
        tol_s = f" (±{d['tolerance']})" if d["tolerance"] else ""
        lines.append(
            f"  [{d['kind']}] {d['group']}.{d['key']}{tol_s}: "
            f"expected={d['expected']!r} actual={d['actual']!r}"
        )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: assert_tokens_match.py <tokens.yaml> [layouts.yaml]\n"
            "       assert_tokens_match.py <theme_dir>",
            file=sys.stderr,
        )
        return 2

    arg1 = Path(sys.argv[1]).resolve()
    if arg1.is_dir():
        diffs = assert_theme_dir_match(arg1)
    else:
        # tokens.yaml [layouts.yaml]
        tokens_path = arg1
        if len(sys.argv) >= 3:
            layouts_path = Path(sys.argv[2]).resolve()
        else:
            layouts_path = tokens_path.parent / "layouts.yaml"
        diffs = assert_tokens_match(tokens_path, layouts_path)

    print(_format_report(diffs))
    return len(diffs)


if __name__ == "__main__":
    sys.exit(main())
