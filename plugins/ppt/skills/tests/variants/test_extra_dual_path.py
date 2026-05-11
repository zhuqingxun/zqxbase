"""测试 renderers_huawei._extra 双查 (path X / path Y).

依赖 dev-1 P3b: engine/renderers_huawei.py:_extra 改造为双查
- path X (推荐): 优先查 SlideSpec.variant 直属字段 + variant.__pydantic_extra__
- path Y (兜底): 回退到 SlideSpec.content 直属字段 + content.__pydantic_extra__
- 兼容旧调用: 接收 SlideContent 实例时仍能工作

研究 §2.3 决议: huawei 18 版式专属字段放 slide.variant 下 (path X), 老 plan 直接
平铺到 slide.content (path Y) 仍兼容 - 不破坏 18 个 renderer 的 30+ 个 _extra 调用。
"""
from __future__ import annotations

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


# 延迟导入: dev-1 P3b 完成前用 skipif 守护
try:
    from engine.renderers_huawei import _extra  # type: ignore
    from schemas.slide_plan import SlideContent, SlideSpec, SlideRole  # type: ignore
    from schemas.variants import Kpi, KpiStatsContent  # type: ignore
except ImportError:
    _extra = None  # type: ignore
    SlideContent = None  # type: ignore
    SlideSpec = None  # type: ignore


pytestmark = pytest.mark.skipif(
    _extra is None or SlideSpec is None,
    reason="engine.renderers_huawei._extra / schemas 尚未就绪 (dev-1 P3b 前)",
)


# ============================================================
# Fixtures: 复用 KpiStatsContent + Kpi 构造合法 SlideSpec
# ============================================================


@pytest.fixture
def kpis():
    """3 个 Kpi 实例 (满足 KpiStatsContent.kpis 的 minItems=3 约束)."""
    return [
        Kpi(label="营收", value="10亿"),
        Kpi(label="增长", value="30%"),
        Kpi(label="市占", value="15%"),
    ]


@pytest.fixture
def variant_kpi_stats(kpis):
    """构造合法 KpiStatsContent (path X 容器)."""
    return KpiStatsContent(visual_type="kpi-stats", title="Q3 报告", kpis=kpis)


@pytest.fixture
def spec_path_x(variant_kpi_stats):
    """SlideSpec with variant only (path X 唯一来源)."""
    return SlideSpec(
        id=1,
        role=SlideRole.DATA,
        content=SlideContent(title="Q3 报告"),
        visual_type="kpi-stats",
        variant=variant_kpi_stats,
    )


@pytest.fixture
def spec_path_y(kpis):
    """SlideSpec with content extra only (path Y 兜底, 老 plan)."""
    # SlideContent.extra='allow' 允许 kpis 平铺到顶层
    sc = SlideContent(title="Q3 报告", kpis=kpis)  # type: ignore[call-arg]
    return SlideSpec(
        id=2,
        role=SlideRole.DATA,
        content=sc,
        visual_type="kpi-stats",
        variant=None,
    )


@pytest.fixture
def spec_path_x_overrides_y(variant_kpi_stats, kpis):
    """variant 与 content 同字段 (variant 优先验证)."""
    other_kpis = [Kpi(label="OLD", value="0")]  # content 路径放不同数据
    sc = SlideContent(title="Q3 报告", kpis=other_kpis)  # type: ignore[call-arg]
    return SlideSpec(
        id=3,
        role=SlideRole.DATA,
        content=sc,
        visual_type="kpi-stats",
        variant=variant_kpi_stats,  # variant 才是真实数据
    )


# ============================================================
# AC: path X 优先级
# ============================================================


class TestPathXVariantPriority:
    """path X (variant) 在双查中优先于 path Y (content)."""

    def test_extra_returns_variant_kpis(self, spec_path_x, kpis):
        """spec.variant.kpis 存在时, _extra 返回 variant 路径数据."""
        result = _extra(spec_path_x, "kpis")
        assert result == kpis, "应返回 variant.kpis (path X 优先)"

    def test_extra_path_x_overrides_path_y(self, spec_path_x_overrides_y, kpis):
        """variant 与 content 都有同字段时, variant 优先 (research §2.3 path X 决议)."""
        result = _extra(spec_path_x_overrides_y, "kpis")
        assert result == kpis, (
            "variant.kpis 应优先于 content.kpis - path X 决议: 严格化将走 variant"
        )
        # 反向验证: 不返回 content 的 OLD 数据
        assert all(k.label != "OLD" for k in result), (
            "返回了 content 路径的 OLD 数据, 说明 path X 优先级未生效"
        )

    def test_extra_variant_field_none_falls_back_to_content(
        self, variant_kpi_stats, kpis
    ):
        """variant 含字段但 optional 字段值是 None 时, 应回退到 content (path Y).

        例如: KpiStatsContent.subtitle=None (Optional) + content.subtitle="X"
        应返回 "X" (variant 的 None 不视为有效, 双查继续找 path Y)。
        """
        # variant.subtitle 默认 None (KpiStatsContent.subtitle: str | None = None)
        assert variant_kpi_stats.subtitle is None
        # content 设置 subtitle
        sc = SlideContent(title="Q3 报告", subtitle="path-Y-subtitle")
        spec = SlideSpec(
            id=5,
            role=SlideRole.DATA,
            content=sc,
            visual_type="kpi-stats",
            variant=variant_kpi_stats,
        )
        result = _extra(spec, "subtitle")
        assert result == "path-Y-subtitle", (
            "variant.subtitle=None 时应回退到 content.subtitle (双查 None 视为缺失)"
        )


# ============================================================
# AC: path Y 兜底 (老 plan 不破)
# ============================================================


class TestPathYContentFallback:
    """无 variant 时回退到 content (path Y 兜底, 18 renderer 老调用不破)."""

    def test_extra_falls_back_to_content_when_no_variant(self, spec_path_y, kpis):
        """spec.variant=None 时, _extra 从 content (含 extra) 取数据."""
        result = _extra(spec_path_y, "kpis")
        assert result == kpis, "spec.variant=None 时应回退到 content (path Y)"

    def test_extra_default_when_neither_path_has_field(self, spec_path_y):
        """variant 与 content 都无字段时返回 default."""
        result = _extra(spec_path_y, "_unknown_field", default="SENTINEL")
        assert result == "SENTINEL"

    def test_extra_default_none_when_no_default_specified(self, spec_path_y):
        """缺失字段不传 default 时返回 None."""
        result = _extra(spec_path_y, "_unknown_field")
        assert result is None


# ============================================================
# AC: __pydantic_extra__ 路径覆盖
# ============================================================


class TestPydanticExtraDict:
    """字段在 __pydantic_extra__ (extra='allow' 兜底) 而非声明字段时仍能找到."""

    def test_content_extra_dict_lookup(self, kpis):
        """SlideContent extra 字段 (非声明字段) 通过 __pydantic_extra__ 取到."""
        # 'kpis' 是 SlideContent 的 extra 字段 (Pydantic V2 extra='allow')
        sc = SlideContent(title="Q3", kpis=kpis)  # type: ignore[call-arg]
        spec = SlideSpec(
            id=4,
            role=SlideRole.DATA,
            content=sc,
            visual_type="kpi-stats",
            variant=None,
        )
        result = _extra(spec, "kpis")
        assert result == kpis, (
            "SlideContent.__pydantic_extra__['kpis'] 应可读 (extra='allow' 路径)"
        )


# ============================================================
# AC: 旧调用方向后兼容 (传 SlideContent 而非 SlideSpec)
# ============================================================


class TestLegacyCallerWithSlideContent:
    """旧 18 renderer 中曾用 _extra(spec.content, ...) 形式, 双查改造后仍工作."""

    def test_extra_accepts_slide_content_directly(self, kpis):
        """传 SlideContent 实例 (非 SlideSpec) 时, _extra 也能从 content 取字段."""
        sc = SlideContent(title="Q3", kpis=kpis)  # type: ignore[call-arg]
        # SlideContent 没有 .variant 属性 -> 跳过 path X, 直接走 path Y
        result = _extra(sc, "kpis")
        assert result == kpis, (
            "传 SlideContent (无 .variant) 时应走 path Y - 旧 18 renderer "
            "调用_extra(spec.content, ...) 兼容"
        )

    def test_legacy_caller_default_fallback(self, kpis):
        """旧调用方在缺失字段时仍返回 default."""
        sc = SlideContent(title="Q3")  # 无 kpis
        result = _extra(sc, "kpis", default=[])
        assert result == [], "旧调用方缺失字段应返回 default (空列表)"
