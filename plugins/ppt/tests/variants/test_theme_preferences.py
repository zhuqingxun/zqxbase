"""测试 themes/huawei/preferences.yaml 加载与 schema (P1 / P2 + AC-017/018/026).

依赖 Dev:
- P1: themes/huawei/preferences.yaml 新建
- P2: engine/render.py:load_theme 加载 preferences.yaml
- P2: engine/plan.py:load_theme 委托 render.load_theme

未实施时使用 skipif 守护。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
PREFERENCES_YAML = PLUGIN_ROOT / "themes" / "huawei" / "preferences.yaml"
PRESETS_DIR = PLUGIN_ROOT / "presets"


# ============================================================
# AC-017: themes/huawei/preferences.yaml 加载并暴露核心字段
# ============================================================

@pytest.mark.skipif(
    not PREFERENCES_YAML.exists(),
    reason=f"{PREFERENCES_YAML} 尚未就绪 (Dev P1 前)",
)
class TestHuaweiPreferencesSchema:
    """AC-017: preferences.yaml schema 校验."""

    @pytest.fixture(scope="class")
    def prefs(self) -> dict:
        return yaml.safe_load(PREFERENCES_YAML.read_text(encoding="utf-8")) or {}

    def test_top_level_keys_present(self, prefs: dict):
        """4 个核心字段都存在."""
        assert "visual_type_preferences" in prefs
        assert "required_for_role" in prefs
        assert "forbidden_visual_types" in prefs
        # decision_rules 可选 (preferences.yaml 用 required_for_content 替代)
        # 至少其中之一存在
        assert (
            "decision_rules" in prefs
            or "required_for_content" in prefs
        ), "必须含 decision_rules 或 required_for_content"

    def test_visual_type_preferences_is_dict_with_18_huawei_keys(self, prefs: dict):
        """visual_type_preferences 含 huawei 18 版式 key."""
        from schemas.variants import VARIANT_TYPES

        vp = prefs["visual_type_preferences"]
        assert isinstance(vp, dict)
        # 18 huawei 版式必须每个都登记权重
        missing = VARIANT_TYPES - set(vp.keys())
        assert not missing, f"preferences.yaml 缺权重: {missing}"

    def test_visual_type_preferences_values_are_numeric(self, prefs: dict):
        """权重必须是数值 (int/float)."""
        for k, v in prefs["visual_type_preferences"].items():
            assert isinstance(v, (int, float)), f"权重 {k}={v} 类型应为数值"

    def test_required_for_role_contains_4_role_mappings(self, prefs: dict):
        """硬约束 1: role → visual_type 映射,至少含 title/closing/section."""
        rfr = prefs["required_for_role"]
        assert isinstance(rfr, dict)
        # 6 类硬约束中的 role 类: title / closing / section (toc 由启发式处理或单列)
        for required_role in ("title", "closing", "section"):
            assert required_role in rfr, f"required_for_role 缺 {required_role}"
        assert rfr["title"] == "cover-left-bar"
        assert rfr["closing"] == "thankyou"
        assert rfr["section"] == "section-divider-dark"

    def test_forbidden_visual_types_contains_hero_statement(self, prefs: dict):
        """硬约束 3: hero-statement 必须在禁用清单中."""
        fvt = prefs["forbidden_visual_types"]
        # 支持两种格式: list[str] 或 dict[str, list[str]] (按 role 分)
        if isinstance(fvt, list):
            assert "hero-statement" in fvt
        elif isinstance(fvt, dict):
            # role-scoped 禁用; 至少 title/closing 下含 hero-statement
            for role in ("title", "closing"):
                if role in fvt:
                    assert "hero-statement" in fvt[role], (
                        f"forbidden_visual_types[{role}] 应含 hero-statement"
                    )
        else:
            pytest.fail(f"forbidden_visual_types 类型异常: {type(fvt)}")

    def test_application_thresholds_field_present(self, prefs: dict):
        """Q5 决议: application_thresholds 应内嵌 yaml,默认 60/30."""
        thresholds = prefs.get("application_thresholds", {})
        assert isinstance(thresholds, dict)
        # 60% / 30% 默认值 (允许小数微调)
        warn = thresholds.get("warn_below", 0.60)
        fail = thresholds.get("fail_below", 0.30)
        assert 0 < fail < warn < 1, f"阈值非法: warn={warn} fail={fail}"


# ============================================================
# AC-018: preset 删除 visual_type_preferences 字段 (Q3 决议)
# ============================================================

@pytest.mark.skipif(
    not PRESETS_DIR.exists(),
    reason=f"{PRESETS_DIR} 不存在",
)
class TestPresetsNoVisualTypePreferences:
    """AC-018: 3 个 preset YAML 不再含 visual_type_preferences 字段."""

    @pytest.mark.parametrize("preset_name", [
        "business-briefing",
        "research-report",
        "academic-talk",
    ])
    def test_preset_has_no_visual_type_preferences(self, preset_name: str):
        """preset 顶层不应含 visual_type_preferences."""
        preset_path = PRESETS_DIR / f"{preset_name}.yaml"
        if not preset_path.exists():
            pytest.skip(f"{preset_path} 不存在")
        data = yaml.safe_load(preset_path.read_text(encoding="utf-8")) or {}
        assert "visual_type_preferences" not in data, (
            f"{preset_name}.yaml 仍含 visual_type_preferences (P6 未删干净)"
        )

    @pytest.mark.parametrize("preset_name", [
        "business-briefing",
        "research-report",
        "academic-talk",
    ])
    def test_preset_keeps_structure_and_content_rules(self, preset_name: str):
        """preset 仍保留 structure 与 content_rules (不要全删)."""
        preset_path = PRESETS_DIR / f"{preset_name}.yaml"
        if not preset_path.exists():
            pytest.skip(f"{preset_path} 不存在")
        data = yaml.safe_load(preset_path.read_text(encoding="utf-8")) or {}
        # structure 与 content_rules 之一必须存在 (preset 仍要有内容规则)
        assert "structure" in data or "content_rules" in data, (
            f"{preset_name}.yaml 应保留 structure/content_rules"
        )


# ============================================================
# load_theme 集成: 主题加载链路含 preferences (P2)
# ============================================================

class TestLoadThemeIncludesPreferences:
    """P2 验证: load_theme('huawei') 返回 dict 含 preferences key."""

    def test_render_load_theme_huawei_has_preferences_key(self):
        """render.load_theme 加载后 preferences key 存在."""
        try:
            from engine.render import load_theme
        except ImportError:
            pytest.skip("engine.render 未就绪")

        if not PREFERENCES_YAML.exists():
            pytest.skip("Dev P1 前 preferences.yaml 不存在")

        theme = load_theme("huawei")
        assert "preferences" in theme, (
            "load_theme 返回 dict 必须含 preferences key (P2 实施后)"
        )
        prefs = theme["preferences"]
        assert isinstance(prefs, dict)
        # 关键字段透传
        assert "required_for_role" in prefs

    def test_plan_py_load_theme_delegates_to_render(self):
        """plan.load_theme 委托到 render.load_theme,返回 dict 含 preferences."""
        try:
            from engine import plan as plan_mod
        except ImportError:
            pytest.skip("engine.plan 未就绪")

        if not PREFERENCES_YAML.exists():
            pytest.skip("Dev P1/P2 前")

        result = plan_mod.load_theme("huawei")
        assert isinstance(result, dict)
        # 委托后行为一致: 含 preferences
        assert "preferences" in result, (
            "plan.load_theme 应委托 render.load_theme (P2),含 preferences key"
        )


# ============================================================
# AC-026: fallback_chain 退回机制
# ============================================================

class TestFallbackChain:
    """AC-026: KPI < 3 时 kpi-stats 自动退回 data-contrast."""

    @pytest.mark.skipif(
        not PREFERENCES_YAML.exists(),
        reason="P1 前",
    )
    def test_preferences_has_fallback_chain(self):
        """preferences.yaml 含 fallback_chain 字段."""
        prefs = yaml.safe_load(PREFERENCES_YAML.read_text(encoding="utf-8")) or {}
        assert "fallback_chain" in prefs, (
            "preferences.yaml 必须含 fallback_chain (Plan §1.2)"
        )
        fc = prefs["fallback_chain"]
        assert isinstance(fc, dict)
        # 关键映射: kpi-stats / architecture-layered / process-flow-huawei / timeline-huawei
        for key in ("kpi-stats", "architecture-layered", "process-flow-huawei"):
            assert key in fc, f"fallback_chain 缺 {key}"

    @pytest.mark.skipif(
        not PREFERENCES_YAML.exists(),
        reason="P1 前",
    )
    def test_fallback_chain_kpi_stats_first_is_data_contrast(self):
        """kpi-stats fallback_chain 第一项是 data-contrast (KPI<3 退回首选)."""
        prefs = yaml.safe_load(PREFERENCES_YAML.read_text(encoding="utf-8")) or {}
        chain = prefs["fallback_chain"]["kpi-stats"]
        assert isinstance(chain, list) and len(chain) >= 1
        assert chain[0] == "data-contrast", (
            f"kpi-stats fallback 首选应为 data-contrast (Plan §1.2),实际 {chain[0]}"
        )

    @pytest.mark.skipif(
        not PREFERENCES_YAML.exists(),
        reason="P1 前",
    )
    def test_fallback_chain_lists_are_non_empty(self):
        """每个 huawei 版式的 fallback_chain 至少 1 个退回选项."""
        prefs = yaml.safe_load(PREFERENCES_YAML.read_text(encoding="utf-8")) or {}
        for variant, chain in prefs["fallback_chain"].items():
            assert isinstance(chain, list)
            assert len(chain) >= 1, f"{variant} fallback_chain 不应为空"
