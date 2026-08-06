"""端到端测试: ability-evaluation 真实场景 (AC-021/022/023).

依赖:
- Dev T6 全部完成 (P1-P10)
- tests/fixtures/ability-evaluation.md (真实 markdown, Dev T6 实施时一并产出)
- tests/fixtures/ability-evaluation-recorded.json (LLM 输出回放)

LLM 调用通过 monkeypatch 替换为 fixture 回放,CI 可重复。
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PLUGIN_ROOT / "tests" / "fixtures"
ABILITY_MD = FIXTURES_DIR / "ability-evaluation.md"
ABILITY_RECORDED = FIXTURES_DIR / "ability-evaluation-recorded.json"


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not ABILITY_MD.exists(),
        reason=f"{ABILITY_MD} 尚未就绪 (Dev T6 实施时录制)",
    ),
]


# ============================================================
# AC-021: ability-evaluation 应用率 ≥ 80%
# ============================================================

class TestAbilityEvaluationApplicationRate:
    """AC-021: 端到端跑后 huawei 应用率 ≥ 80%."""

    @pytest.fixture
    def slide_plan_yaml(self, tmp_path, monkeypatch):
        """跑 /ppt:create 等价流程, 返回产出 slide-plan.yaml 路径."""
        if not ABILITY_RECORDED.exists():
            pytest.skip(f"LLM 回放 fixture {ABILITY_RECORDED} 不存在")

        # monkeypatch LLM 调用
        try:
            from engine import plan as plan_mod  # type: ignore
        except ImportError:
            pytest.skip("engine.plan 不可导入")

        recorded = json.loads(ABILITY_RECORDED.read_text(encoding="utf-8"))

        # 替换 LLM 调用 (Dev T6 实施时确认接口名)
        # 候选 1: plan_mod.call_llm_for_slide_specs
        # 候选 2: plan_mod.generate_slide_plan
        # 这里做防御式 patch: 找任何 call_llm/generate 类函数都替换
        for attr in dir(plan_mod):
            if attr.startswith("_"):
                continue
            if "llm" in attr.lower() or attr.startswith("generate_"):
                monkeypatch.setattr(
                    plan_mod, attr,
                    lambda *args, **kwargs: recorded,
                    raising=False,
                )

        # 实际跑 plan 流程 (Dev T6 实施时的入口名待确认)
        # 这里仅占位,Dev 实施后填具体调用
        pytest.skip("Dev T6 后填实际 plan 入口")

    def test_huawei_application_rate_above_80(self, slide_plan_yaml):
        """huawei 18 版式占比 >= 80%."""
        import yaml
        from schemas.variants import VARIANT_TYPES

        data = yaml.safe_load(Path(slide_plan_yaml).read_text(encoding="utf-8"))
        slides = data.get("slides", [])
        total = len(slides)
        assert total > 0, "产出 plan 无 slides"

        huawei_count = sum(
            1 for s in slides if s.get("visual_type") in VARIANT_TYPES
        )
        ratio = huawei_count / total
        assert ratio >= 0.8, (
            f"huawei 应用率 {ratio:.1%} < 80% (业务目标)"
            f", huawei={huawei_count}/{total}"
        )

    def test_first_slide_is_cover_left_bar(self, slide_plan_yaml):
        """第一页 visual_type = cover-left-bar (硬约束)."""
        import yaml

        data = yaml.safe_load(Path(slide_plan_yaml).read_text(encoding="utf-8"))
        slides = data.get("slides", [])
        assert slides[0].get("visual_type") == "cover-left-bar"

    def test_last_slide_is_thankyou(self, slide_plan_yaml):
        """末页 visual_type = thankyou."""
        import yaml

        data = yaml.safe_load(Path(slide_plan_yaml).read_text(encoding="utf-8"))
        slides = data.get("slides", [])
        assert slides[-1].get("visual_type") == "thankyou"

    def test_toc_slide_present_and_uses_toc_variant(self, slide_plan_yaml):
        """含 toc 页且 visual_type = toc."""
        import yaml

        data = yaml.safe_load(Path(slide_plan_yaml).read_text(encoding="utf-8"))
        slides = data.get("slides", [])
        toc_slides = [s for s in slides if s.get("visual_type") == "toc"]
        assert len(toc_slides) >= 1, "至少应含 1 张 toc 页"


# ============================================================
# AC-022: 渲染 .pptx XML 颜色清零
# ============================================================

LEGACY_BLUE_HEX_LOWER = ("2563eb", "f0f4ff", "1a1a2e", "4a4a68")
HUAWEI_PRIMARY_RED_LOWER = "c7000b"


class TestPptxXmlColorPurification:
    """AC-022: ability-evaluation 渲染 .pptx 视觉无蓝, 主红多处出现."""

    @pytest.fixture
    def rendered_pptx(self, tmp_path):
        """跑端到端产出 .pptx (Dev T6 实施时入口名确认)."""
        pytest.skip("Dev T6 后填渲染入口")

    def test_no_legacy_blue_in_slide_xml(self, rendered_pptx):
        """ppt/slides/*.xml 不含历史蓝色码."""
        with zipfile.ZipFile(str(rendered_pptx)) as zf:
            slide_xmls = [
                n for n in zf.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]
            assert len(slide_xmls) > 0, "PPTX 无 slides/slide*.xml"

            for name in slide_xmls:
                content = zf.read(name).decode("utf-8", errors="replace").lower()
                for blue in LEGACY_BLUE_HEX_LOWER:
                    count = content.count(blue)
                    assert count == 0, (
                        f"{name} 含 {count} 处历史蓝 #{blue.upper()}"
                    )

    def test_huawei_red_appears_at_least_3_times(self, rendered_pptx):
        """ppt/slides/*.xml 主红 #C7000B 至少出现 3 次."""
        with zipfile.ZipFile(str(rendered_pptx)) as zf:
            slide_xmls = [
                n for n in zf.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]

            total_red_count = 0
            for name in slide_xmls:
                content = zf.read(name).decode("utf-8", errors="replace").lower()
                total_red_count += content.count(HUAWEI_PRIMARY_RED_LOWER)

            assert total_red_count >= 3, (
                f"主红 #C7000B 仅出现 {total_red_count} 次, 应 ≥ 3 (huawei 主题验证)"
            )


# ============================================================
# AC-023: 机制扩展性 (假主题不需改 SKILL.md)
# ============================================================

class TestThemeExtensibility:
    """AC-023: 切换到假主题, prompt 拼接不破."""

    def test_fake_theme_works_without_skill_md_change(self, tmp_path, monkeypatch):
        """临时假主题 themes/clean-test-fake/preferences.yaml 也能跑通 prompt 拼接."""
        try:
            from engine import prompt_assembler  # type: ignore
        except ImportError:
            pytest.skip("engine.prompt_assembler 未就绪 (Dev P3 前)")

        # 创建假主题目录
        fake_themes_root = tmp_path / "themes"
        fake_theme = fake_themes_root / "clean-test-fake"
        fake_theme.mkdir(parents=True)
        # 最小 preferences.yaml: 仅含权重表, 无硬约束
        (fake_theme / "preferences.yaml").write_text(
            "visual_type_preferences:\n"
            "  cards-3: 5\n"
            "  bullets: 3\n"
            "required_for_role: {}\n"
            "forbidden_visual_types: []\n",
            encoding="utf-8",
        )
        # 必备 tokens.yaml + layouts.yaml (load_theme 要求)
        (fake_theme / "tokens.yaml").write_text(
            "colors:\n  primary: '#000000'\n",
            encoding="utf-8",
        )
        (fake_theme / "layouts.yaml").write_text("{}\n", encoding="utf-8")

        # monkeypatch SKILLS_DIR / THEMES_DIR 指向临时根
        try:
            from engine import render as render_mod
        except ImportError:
            pytest.skip("engine.render 未就绪")

        monkeypatch.setattr(render_mod, "SKILLS_DIR", tmp_path, raising=False)

        # 重新加载假主题 (load_theme 应不抛异常)
        try:
            theme = render_mod.load_theme("clean-test-fake")
        except Exception as e:
            pytest.fail(f"load_theme 假主题失败: {e}")

        # prompt 拼接不抛异常
        try:
            output = prompt_assembler.assemble_stage3_prompt(theme, mode="embed")
        except Exception as e:
            pytest.fail(f"prompt_assembler 假主题拼接失败: {e}")

        assert isinstance(output, str)
        assert len(output) > 0
