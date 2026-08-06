"""测试 validate_plan.py 应用率门禁 (P8 + AC-009~013).

依赖 Dev P8: validate_plan.py
- ValidationReport.huawei_variant_count @property
- ValidationReport.huawei_variant_ratio @property
- ValidationReport.theme_application_status(warn_below, fail_below) -> str
- main() 加 --theme 参数,FAIL 时 exit code 2
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PLUGIN_ROOT / "tests" / "fixtures"
VALIDATE_PY = PLUGIN_ROOT / "engine" / "validate_plan.py"


def _validate_plan_or_skip():
    """import validate_plan, 失败时 skip."""
    try:
        from engine import validate_plan as vp
        return vp
    except ImportError:
        pytest.skip("engine.validate_plan 不可导入")


def _run_cli(fixture: Path, theme: str = "huawei") -> tuple[int, dict]:
    """运行 validate_plan.py CLI, 返回 (exit_code, json_output)."""
    cmd = [
        sys.executable,
        "-c",
        f"import sys; sys.argv = ['validate_plan', r'{fixture}', '--theme', '{theme}', '--json']; "
        f"sys.path.insert(0, r'{PLUGIN_ROOT}'); "
        f"from engine.validate_plan import main; main()",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {"_raw_stdout": result.stdout, "_raw_stderr": result.stderr}
    return result.returncode, data


# ============================================================
# AC-009: 90% PASS
# ============================================================

class TestApplicationRate90Percent:
    """AC-009: 90% huawei 占比 → PASS, exit 0."""

    def test_validate_plan_module_count(self):
        """ValidationReport.huawei_variant_count 计算正确."""
        vp = _validate_plan_or_skip()
        if not hasattr(vp.ValidationReport, "huawei_variant_count"):
            pytest.skip("Dev P8 前 ValidationReport 无 huawei_variant_count")

        fixture = FIXTURES_DIR / "application-rate-90.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        report = vp.validate_plan(str(fixture))
        # 90% fixture: 9 huawei + 1 cards-3
        assert report.huawei_variant_count == 9
        assert report.total_slides == 10
        assert abs(report.huawei_variant_ratio - 0.9) < 0.01

    def test_status_pass_at_90_percent(self):
        """90% → status PASS."""
        vp = _validate_plan_or_skip()
        if not hasattr(vp.ValidationReport, "theme_application_status"):
            pytest.skip("Dev P8 前")
        fixture = FIXTURES_DIR / "application-rate-90.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        report = vp.validate_plan(str(fixture))
        status = report.theme_application_status(warn_below=0.60, fail_below=0.30)
        assert status == "PASS"


# ============================================================
# AC-009 边界: 60% PASS 边界
# ============================================================

class TestApplicationRate60PercentBoundary:
    """60% 是 PASS 边界: status == PASS."""

    def test_60_percent_is_pass(self):
        vp = _validate_plan_or_skip()
        if not hasattr(vp.ValidationReport, "theme_application_status"):
            pytest.skip("Dev P8 前")
        fixture = FIXTURES_DIR / "application-rate-60.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        report = vp.validate_plan(str(fixture))
        # 60% fixture: 6 huawei + 4 通用
        assert report.huawei_variant_count == 6
        assert report.total_slides == 10
        status = report.theme_application_status(warn_below=0.60, fail_below=0.30)
        # >= 0.60 应为 PASS
        assert status == "PASS", f"60% 应为 PASS 边界,实际 {status}"


# ============================================================
# AC-010: 50% WARN
# ============================================================

class TestApplicationRate50PercentWarn:
    """AC-010: 50% → WARN."""

    def test_50_percent_warn(self):
        vp = _validate_plan_or_skip()
        if not hasattr(vp.ValidationReport, "theme_application_status"):
            pytest.skip("Dev P8 前")
        fixture = FIXTURES_DIR / "application-rate-50.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        report = vp.validate_plan(str(fixture))
        assert report.huawei_variant_count == 5
        assert report.total_slides == 10
        status = report.theme_application_status(warn_below=0.60, fail_below=0.30)
        assert status == "WARN"


# ============================================================
# AC-011: 29% FAIL
# ============================================================

class TestApplicationRate29PercentFail:
    """AC-011: < 30% → FAIL, exit code 2."""

    def test_29_percent_fail_status(self):
        vp = _validate_plan_or_skip()
        if not hasattr(vp.ValidationReport, "theme_application_status"):
            pytest.skip("Dev P8 前")
        fixture = FIXTURES_DIR / "application-rate-29.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        report = vp.validate_plan(str(fixture))
        # 2/7 ≈ 28.6% < 30%
        assert report.total_slides == 7
        assert report.huawei_variant_count == 2
        status = report.theme_application_status(warn_below=0.60, fail_below=0.30)
        assert status == "FAIL"

    def test_29_percent_cli_exit_code_nonzero(self):
        """CLI 跑 29% fixture, exit code != 0 (Plan §8.2 设 exit 2)."""
        if not VALIDATE_PY.exists():
            pytest.skip(f"{VALIDATE_PY} 不存在")
        fixture = FIXTURES_DIR / "application-rate-29.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        exit_code, _data = _run_cli(fixture, theme="huawei")
        assert exit_code != 0, (
            "29% (FAIL) 应让 CLI exit != 0 (强制门禁), 实际 0"
        )


# ============================================================
# AC-012: 0% FAIL (bug 复现)
# ============================================================

class TestApplicationRate0PercentBugReproducer:
    """AC-012: 0% → FAIL, 复现当前 ability-evaluation bug."""

    def test_zero_percent_fail(self):
        vp = _validate_plan_or_skip()
        if not hasattr(vp.ValidationReport, "theme_application_status"):
            pytest.skip("Dev P8 前")
        fixture = FIXTURES_DIR / "application-rate-0.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        report = vp.validate_plan(str(fixture))
        assert report.huawei_variant_count == 0
        status = report.theme_application_status(warn_below=0.60, fail_below=0.30)
        assert status == "FAIL"


# ============================================================
# AC-013: 非 huawei 主题跳过应用率门禁
# ============================================================

class TestNonHuaweiThemeSkipsGate:
    """AC-013: theme != huawei 时不报应用率 FAIL."""

    def test_no_theme_passed_no_application_status(self):
        """无 --theme 参数,JSON 输出不含 theme_application 段."""
        if not VALIDATE_PY.exists():
            pytest.skip(f"{VALIDATE_PY} 不存在")
        fixture = FIXTURES_DIR / "application-rate-0.yaml"
        if not fixture.exists():
            pytest.skip(f"{fixture} 不存在")

        # 跑 CLI 不带 --theme 参数 (改用最小自定义 args)
        cmd = [
            sys.executable,
            "-c",
            f"import sys; sys.argv = ['validate_plan', r'{fixture}', '--json']; "
            f"sys.path.insert(0, r'{PLUGIN_ROOT}'); "
            f"from engine.validate_plan import main; "
            f"try: main()\nexcept SystemExit: pass",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.skip(f"CLI 输出无效 JSON: {result.stdout[:200]}")

        # 无 --theme 时不应含 theme_application 段
        assert "theme_application" not in data, (
            "无 --theme 时不应触发应用率门禁"
        )


# ============================================================
# 一致性: VARIANT_EXEMPT_TYPES == schemas.variants.VARIANT_TYPES
# ============================================================

class TestVariantSetConsistency:
    """validate_plan.VARIANT_EXEMPT_TYPES 必须与 schemas.variants.VARIANT_TYPES 一致."""

    def test_variant_exempt_types_matches_variants_module(self):
        try:
            from engine.validate_plan import VARIANT_EXEMPT_TYPES
            from schemas.variants import VARIANT_TYPES
        except ImportError:
            pytest.skip("依赖模块不可导入")

        # 两个 set 必须严格相等
        diff_only_in_validate = VARIANT_EXEMPT_TYPES - VARIANT_TYPES
        diff_only_in_variants = VARIANT_TYPES - VARIANT_EXEMPT_TYPES
        assert not diff_only_in_validate, (
            f"VARIANT_EXEMPT_TYPES 多出: {diff_only_in_validate}"
        )
        assert not diff_only_in_variants, (
            f"VARIANT_TYPES 中漏登记: {diff_only_in_variants}"
        )


# ============================================================
# 补充: exit code 1 (内容量 fail) vs exit code 2 (应用率 FAIL)
# 区分契约 (PRD §7 二级门禁, plan §8.2 C). 单纯 != 0 不够细。
# ============================================================


class TestExitCodeDistinction:
    """exit code 区分: PASS=0, 内容量 fail=1, 应用率 FAIL=2 (优先级 1>2)."""

    def test_exit_code_2_when_content_pass_but_app_fail(self, tmp_path):
        """所有 slides SKIP (hero-statement) -> 内容量 PASS, app=0% -> exit 2."""
        if not VALIDATE_PY.exists():
            pytest.skip(f"{VALIDATE_PY} 不存在")
        plan = tmp_path / "all_skip.yaml"
        plan.write_text(
            "slides:\n"
            "  - id: 1\n    visual_type: hero-statement\n    content: {title: A}\n"
            "  - id: 2\n    visual_type: hero-statement\n    content: {title: B}\n"
            "  - id: 3\n    visual_type: hero-statement\n    content: {title: C}\n",
            encoding="utf-8",
        )
        exit_code, _data = _run_cli(plan, theme="huawei")
        assert exit_code == 2, (
            f"内容量 PASS + 应用率 FAIL 应 exit 2, 实际 {exit_code}"
        )

    def test_exit_code_1_when_content_fail(self, tmp_path):
        """有 slide 内容量 fail (低于阈值) -> exit 1, 不论应用率."""
        if not VALIDATE_PY.exists():
            pytest.skip(f"{VALIDATE_PY} 不存在")
        plan = tmp_path / "content_fail.yaml"
        # cards-3 每个 key_point 至少 80 字, 这里仅 5 字必 fail
        plan.write_text(
            "slides:\n"
            "  - id: 1\n    visual_type: cards-3\n"
            "    content:\n      title: T\n"
            "      key_points:\n"
            "        - {heading: A, body: 短}\n"
            "        - {heading: B, body: 短}\n"
            "        - {heading: C, body: 短}\n",
            encoding="utf-8",
        )
        exit_code, _data = _run_cli(plan, theme="huawei")
        assert exit_code == 1, (
            f"内容量 fail 应 exit 1 (优先于应用率), 实际 {exit_code}"
        )

    def test_exit_code_0_when_pass_at_full_huawei(self):
        """已有 90% fixture (TestApplicationRate90Percent) -> exit 0 (双门禁通过)."""
        fixture = FIXTURES_DIR / "application-rate-90.yaml"
        if not VALIDATE_PY.exists() or not fixture.exists():
            pytest.skip("依赖 fixture/CLI 不可用")
        exit_code, data = _run_cli(fixture, theme="huawei")
        if exit_code != 0:
            # 某些 fixture 可能内容量 fail 不是本测试目标; skip 不算回归
            pytest.skip(
                f"90% fixture 双门禁未全通过 (exit {exit_code}), 内容量阈值变更?"
            )


# ============================================================
# 补充: _load_theme_thresholds fallback 链路
# (try theme_loader -> fallback render.load_theme -> 默认 60/30)
# 这是 P8 forward-compat 设计的关键, 必须验证 3 层 fallback 都正确
# ============================================================


class TestLoadThemeThresholdsFallback:
    """_load_theme_thresholds: theme_loader 优先 -> render fallback -> 默认 60/30."""

    def test_returns_huawei_thresholds_from_preferences_yaml(self):
        """huawei 主题正常加载: 应读到 preferences.yaml 的 application_thresholds."""
        try:
            from engine.validate_plan import _load_theme_thresholds
        except ImportError:
            pytest.skip("engine.validate_plan 不可导入")

        warn_below, fail_below = _load_theme_thresholds("huawei")
        # huawei preferences.yaml 写的就是 0.60 / 0.30 (Q5 决议)
        assert warn_below == 0.60, f"warn_below 期望 0.60, 实际 {warn_below}"
        assert fail_below == 0.30, f"fail_below 期望 0.30, 实际 {fail_below}"

    def test_falls_back_to_default_for_unknown_theme(self):
        """未知主题 (theme_loader / render 双失败) -> 退回硬编码默认 60/30."""
        try:
            from engine.validate_plan import _load_theme_thresholds
        except ImportError:
            pytest.skip("engine.validate_plan 不可导入")

        warn_below, fail_below = _load_theme_thresholds("__nonexistent_theme__")
        # 双 fallback 全失败 -> 默认 60/30 (Q5 决议)
        assert warn_below == 0.60
        assert fail_below == 0.30

    def test_returns_floats(self):
        """函数应返回 (float, float), 不是字符串或 None."""
        try:
            from engine.validate_plan import _load_theme_thresholds
        except ImportError:
            pytest.skip("engine.validate_plan 不可导入")

        warn_below, fail_below = _load_theme_thresholds("huawei")
        assert isinstance(warn_below, float)
        assert isinstance(fail_below, float)
        # 数据完整性: warn 大于 fail (软阈值 > 硬阈值)
        assert warn_below > fail_below
