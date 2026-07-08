# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pydantic>=2.0", "pyyaml>=6.0"]
# ///
"""ARCH-002 阶段1：validate_plan 把 path Y（变体字段平铺到 content 顶层、缺
slide['variant'] 块）从"默默兜底 PASS"改为 FAIL。

被测改动：engine/validate_plan.py validate_slide() 的 group=='variant' 分支，
原 path B（variant_data is None → 从 content 抽子集二次校验、通过即 PASS）现改为
直接 FAIL + 可定位信息（slide id / visual_type / 平铺字段名）。

关键设计（advisor 红线）：用例必须是"改前会 PASS 的合法 path-Y 数据"——
即把 *合法* 的 kpis（≥3 个）平铺在 content 顶层、无 variant 块。这样 FAIL 纯粹
来自 path-Y 契约拒绝（契约变化被测到），而非"拒了一份本就非法的数据"。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _validate_plan_or_skip():
    """import engine.validate_plan，失败时 skip（对齐 application_rate 测试守护）。"""
    try:
        from engine import validate_plan as vp  # type: ignore
        return vp
    except ImportError:
        pytest.skip("engine.validate_plan 不可导入")


# --- 测试数据：3 个合法 Kpi（满足 KpiStatsContent.kpis minItems=3） ---
_VALID_KPIS = [
    {"label": "营收", "value": "10亿"},
    {"label": "增长", "value": "30%"},
    {"label": "市占", "value": "15%"},
]


def _slide_path_y() -> dict:
    """path Y：合法 kpis 平铺到 content 顶层，无 variant 块（违反契约）。"""
    return {
        "id": 1,
        "visual_type": "kpi-stats",
        "content": {"title": "Q3 业绩", "kpis": _VALID_KPIS},
    }


def _slide_path_x() -> dict:
    """path X 对照：同样的合法数据放进 variant 块（推荐路径）。"""
    return {
        "id": 1,
        "visual_type": "kpi-stats",
        "content": {"title": "Q3 业绩"},
        "variant": {
            "visual_type": "kpi-stats",
            "title": "Q3 业绩",
            "kpis": _VALID_KPIS,
        },
    }


# ============================================================
# 核心：path Y → FAIL（契约收紧）
# ============================================================


def test_path_y_flattened_variant_fields_fail():
    """variant 类型 + 合法字段平铺 content + 无 variant 块 → 该 slide FAIL。"""
    vp = _validate_plan_or_skip()
    report = vp.validate_plan_from_data({"slides": [_slide_path_y()]})
    res = report.results[0]
    assert res.status == "FAIL", (
        f"path Y（缺 variant 块）应 FAIL，实际 {res.status}。"
        f"若为 PASS 说明 path-B 兜底未被收紧。"
    )


def test_path_y_fail_message_is_locatable():
    """FAIL 信息含 slide id + visual_type + 平铺字段名（kpis），可定位。"""
    vp = _validate_plan_or_skip()
    report = vp.validate_plan_from_data({"slides": [_slide_path_y()]})
    issue = report.results[0].total_issue
    assert "slide 1" in issue, f"FAIL 信息缺 slide id (期望 'slide 1'): {issue!r}"
    assert "kpi-stats" in issue, f"FAIL 信息缺 visual_type: {issue!r}"
    assert "variant" in issue, f"FAIL 信息未提示应放 variant: {issue!r}"
    assert "kpis" in issue, f"FAIL 信息未列出平铺字段名 kpis: {issue!r}"


# ============================================================
# 对照：path X → PASS（不误伤推荐路径）
# ============================================================


def test_path_x_variant_block_still_passes():
    """同一份合法数据放进 variant 块（path X）→ 仍 PASS（只拦 path Y）。"""
    vp = _validate_plan_or_skip()
    report = vp.validate_plan_from_data({"slides": [_slide_path_x()]})
    res = report.results[0]
    assert res.status == "PASS", (
        f"path X（variant 块合法）不应被误伤，实际 {res.status}: {res.total_issue!r}"
    )


# ============================================================
# 退出码（R3）：含 path-Y 页的 plan 经 CLI → 退出码 1（内容/结构 fail，非应用率 2）
# ============================================================


def test_cli_exit_code_1_on_path_y(tmp_path):
    """CLI 跑含 path-Y 页的 plan → 退出码 1（report.ok=False 路径）。"""
    import yaml

    _validate_plan_or_skip()  # 守护：engine 不可用时 skip
    fixture = tmp_path / "path_y_plan.yaml"
    fixture.write_text(
        yaml.safe_dump({"slides": [_slide_path_y()]}, allow_unicode=True),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "-c",
        f"import sys; sys.argv = ['validate_plan', r'{fixture}', '--json']; "
        f"sys.path.insert(0, r'{PLUGIN_ROOT}'); "
        f"from engine.validate_plan import main; main()",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, (
        f"path-Y plan 应退出码 1（内容/结构 fail），实际 {result.returncode}。"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # 兼容性确认：FAIL 确实落在该 slide 上
    try:
        data = json.loads(result.stdout)
        slide0 = data["slides"][0]
        assert slide0["status"] == "FAIL", f"slide 状态非 FAIL: {slide0}"
    except (json.JSONDecodeError, KeyError, IndexError):
        pass  # 退出码 1 已是主断言，JSON 解析失败不否定主断言


def test_cli_content_fail_precedes_theme_fail(tmp_path):
    """退出码顺序守护：path-Y 内容 FAIL 同时应用率也 FAIL(ratio<30%)时，
    内容 FAIL 短路抢占 → exit 1（非应用率 exit 2）。

    构造：1 个 path-Y kpi-stats(FAIL，计 1 个 huawei variant) + 3 个 hero-statement
    (EXEMPT→SKIP，不计 variant) → ratio=1/4=25% < huawei fail_below(30%) → 应用率 FAIL。
    若将来有人调换 main() 里 exit(1) 与 exit(2) 的检查顺序，本测试翻红。
    """
    import yaml

    _validate_plan_or_skip()
    slides = [_slide_path_y()] + [
        {"id": i, "visual_type": "hero-statement", "content": {"title": f"标题{i}"}}
        for i in (2, 3, 4)
    ]
    fixture = tmp_path / "mixed_plan.yaml"
    fixture.write_text(
        yaml.safe_dump({"slides": slides}, allow_unicode=True), encoding="utf-8"
    )
    cmd = [
        sys.executable,
        "-c",
        f"import sys; sys.argv = ['validate_plan', r'{fixture}', '--theme', 'huawei', '--json']; "
        f"sys.path.insert(0, r'{PLUGIN_ROOT}'); "
        f"from engine.validate_plan import main; main()",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, (
        f"内容 FAIL 应抢占应用率 FAIL → exit 1，实际 {result.returncode}。"
        f"若为 2 说明退出码检查顺序被破坏。stdout={result.stdout!r} stderr={result.stderr!r}"
    )
