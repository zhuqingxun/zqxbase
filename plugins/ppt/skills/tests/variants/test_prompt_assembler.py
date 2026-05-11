"""测试 schema-to-prompt 派生器 (P3 + AC-014/015/016).

依赖 Dev P3: engine/prompt_assembler.py 含
- derive_variant_field_specs() -> dict[str, dict]
- derive_decision_block(theme: dict) -> str
- derive_field_cookbook(specs) -> str
- assemble_stage3_prompt(theme: dict, mode: str = "embed") -> str

实现路径优先用 Pydantic V2 model_json_schema() (research §1 结论)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


# 延迟导入,Dev 实施前用 skipif 守护
try:
    from engine import prompt_assembler  # type: ignore
except ImportError:
    prompt_assembler = None  # type: ignore


pytestmark = pytest.mark.skipif(
    prompt_assembler is None,
    reason="engine.prompt_assembler 尚未就绪 (Dev P3 前)",
)


# ============================================================
# AC-014: schema-to-prompt 派生器从 18 子模型派生字段规格
# ============================================================

class TestDeriveVariantFieldSpecs:
    """AC-014: 派生器输出含 18 版式 + 字段名 + 类型 + 约束."""

    def test_returns_dict_with_18_variants(self):
        """输出 dict 含全部 18 个 huawei 版式."""
        from schemas.variants import VARIANT_TYPES

        specs = prompt_assembler.derive_variant_field_specs()
        assert isinstance(specs, dict)
        # 18 huawei 版式全部覆盖
        missing = VARIANT_TYPES - set(specs.keys())
        assert not missing, f"派生器漏掉版式: {missing}"

    def test_kpi_stats_includes_kpis_field(self):
        """kpi-stats 段含 kpis 字段说明."""
        specs = prompt_assembler.derive_variant_field_specs()
        kpi_spec = specs["kpi-stats"]
        # spec 是 dict 含 fields/required/constraints 之一
        assert isinstance(kpi_spec, dict)
        # 关键字段名 "kpis" 应出现在 fields/schema 中
        text = str(kpi_spec)
        assert "kpis" in text, "kpi-stats spec 应含 kpis 字段"

    def test_architecture_layered_includes_layers(self):
        """architecture-layered 段含 layers 字段."""
        specs = prompt_assembler.derive_variant_field_specs()
        arch_spec = specs["architecture-layered"]
        text = str(arch_spec)
        assert "layers" in text, "architecture-layered spec 应含 layers 字段"

    def test_kpi_stats_has_min_3_constraint(self):
        """kpi-stats kpis 字段约束: minItems=3 (来自 Pydantic Field min_length=3)."""
        specs = prompt_assembler.derive_variant_field_specs()
        kpi_spec = specs["kpi-stats"]
        text = str(kpi_spec)
        # 约束信息要么在 schema 的 minItems/min_length 字段,要么在 constraints 文本
        # 至少包含数字 3 的提示
        has_min = (
            "minItems" in text
            or "min_length" in text
            or "min: 3" in text
            or "3.." in text
            or "≥ 3" in text
            or ">= 3" in text
        )
        assert has_min, f"kpi-stats 应含 min 3 约束提示, 实际: {text[:500]}"

    def test_cover_left_bar_includes_eyebrow_field(self):
        """cover-left-bar 段含 eyebrow / emphasis / meta 字段."""
        specs = prompt_assembler.derive_variant_field_specs()
        cover_spec = specs["cover-left-bar"]
        text = str(cover_spec)
        assert "eyebrow" in text or "meta" in text, (
            "cover-left-bar spec 应含 eyebrow 或 meta 字段"
        )


# ============================================================
# AC-015: schema 变更时派生器自动跟随
# ============================================================

class TestDeriveReflectsSchemaChanges:
    """AC-015: schema-to-prompt 与代码不脱节."""

    def test_derive_uses_pydantic_introspection_not_hardcoded(self):
        """派生器结果包含 Pydantic 子模型实际字段,而非硬编码字符串."""
        # 通过实例化对比: 取一个子模型的 model_fields, 在派生输出中应可见
        from schemas.variants import VariantUnion
        import typing

        union_args = typing.get_args(VariantUnion)[0].__args__
        # 抽样: 找到 KpiStatsContent
        kpi_cls = next(
            cls for cls in union_args
            if cls.__name__.startswith("KpiStats")
        )
        actual_fields = set(kpi_cls.model_fields.keys()) - {"visual_type"}

        specs = prompt_assembler.derive_variant_field_specs()
        kpi_spec_text = str(specs["kpi-stats"])
        # 至少 50% 的实际字段应出现在 spec 文本中
        hit_count = sum(1 for f in actual_fields if f in kpi_spec_text)
        ratio = hit_count / max(1, len(actual_fields))
        assert ratio >= 0.5, (
            f"派生输出仅命中 {hit_count}/{len(actual_fields)} 实际字段, "
            "派生器可能在用硬编码字符串而非 Pydantic introspection"
        )


# ============================================================
# AC-016: 派生器输出长度 ≤ 8000 字符 (prompt 预算)
# ============================================================

class TestOutputSizeWithinBudget:
    """AC-016: 派生输出长度合理,不超 prompt 预算."""

    def test_assemble_stage3_prompt_under_8000_chars(self):
        """assemble_stage3_prompt 输出 ≤ 8000 字符."""
        try:
            from engine.render import load_theme
            theme = load_theme("huawei")
        except (ImportError, FileNotFoundError) as e:
            pytest.skip(f"theme 加载失败 (Dev P1/P2 前): {e}")

        output = prompt_assembler.assemble_stage3_prompt(theme, mode="embed")
        assert isinstance(output, str)
        length = len(output)
        # PRD §13 R1 提到压缩到 ≤30 行/版式; plan §3.4 估 4-6KB; 8000 是上限
        assert length <= 8000, (
            f"prompt 长度 {length} 字符超过 8000 预算 (PRD R1 缓解需要)"
        )
        # 不能太短 (至少含 18 版式说明,粗估 18*100=1800)
        assert length >= 1500, (
            f"prompt 长度 {length} 太短,可能漏内容"
        )


# ============================================================
# 集成: assemble_stage3_prompt 含硬约束 + 字段说明
# ============================================================

class TestAssembleStage3Prompt:
    """assemble_stage3_prompt 集成测试."""

    @pytest.fixture
    def theme(self):
        try:
            from engine.render import load_theme
            return load_theme("huawei")
        except (ImportError, FileNotFoundError) as e:
            pytest.skip(f"theme 加载失败: {e}")

    def test_prompt_includes_six_hard_rules(self, theme):
        """prompt 含 6 类硬约束的关键 visual_type 名."""
        output = prompt_assembler.assemble_stage3_prompt(theme, mode="embed")
        # 6 类硬约束对应版式
        for vt in (
            "cover-left-bar",      # title role
            "thankyou",            # closing role
            "section-divider-dark", # section role
            "toc",                  # 目录
            "kpi-stats",            # KPI panel
            "architecture-layered", # 分层架构
        ):
            assert vt in output, f"prompt 缺硬约束版式 {vt}"

    def test_prompt_mentions_forbidden_hero_statement(self, theme):
        """prompt 提示 hero-statement 在 huawei 主题禁用 (或在 forbidden 段)."""
        output = prompt_assembler.assemble_stage3_prompt(theme, mode="embed")
        # 至少出现 hero-statement (在禁用清单或权重 0 段)
        assert "hero-statement" in output, (
            "prompt 应含 hero-statement (在禁用清单或 0 权重段)"
        )

    def test_prompt_advises_variant_path_x_for_huawei_fields(self, theme):
        """prompt 引导 LLM 把 huawei 专属字段放在 slide.variant 下 (research §2.3 path X)."""
        output = prompt_assembler.assemble_stage3_prompt(theme, mode="embed")
        # 应明确提示 variant 路径
        has_variant_hint = (
            "slide.variant" in output
            or "variant" in output.lower() and ("kpis" in output or "layers" in output)
        )
        assert has_variant_hint, (
            "prompt 应引导 LLM 把专属字段放在 slide.variant (path X 决议)"
        )


# ============================================================
# 补充: assemble_stage3_prompt file 模式 (写盘 .theme-prompt.md)
# Leader 派工清单点名 file 模式覆盖 (P7 SKILL.md 实际通过 CLI 走 file 模式)
# ============================================================


class TestAssembleStage3PromptFileMode:
    """file 模式: 把 prompt 写到 .theme-prompt.md, 返回路径字符串."""

    @pytest.fixture
    def theme(self):
        try:
            from engine.render import load_theme
            return load_theme("huawei")
        except (ImportError, FileNotFoundError) as e:
            pytest.skip(f"theme 加载失败: {e}")

    def test_file_mode_writes_to_path(self, theme, tmp_path):
        """file 模式落盘 + 返回路径 + 内容与 embed 一致."""
        out = tmp_path / ".theme-prompt.md"
        result = prompt_assembler.assemble_stage3_prompt(
            theme, mode="file", output_path=str(out)
        )
        assert isinstance(result, str), "file 模式应返回路径字符串"
        assert Path(result).exists(), "file 模式应实际写盘"
        content = Path(result).read_text(encoding="utf-8")
        embed = prompt_assembler.assemble_stage3_prompt(theme, mode="embed")
        assert content == embed, "file 模式与 embed 模式输出应一致"

    def test_file_mode_creates_parent_dir(self, theme, tmp_path):
        """parent 目录不存在时自动 mkdir, 不抛 FileNotFoundError."""
        nested = tmp_path / "a" / "b" / "c" / ".theme-prompt.md"
        result = prompt_assembler.assemble_stage3_prompt(
            theme, mode="file", output_path=str(nested)
        )
        assert Path(result).exists()

    def test_file_mode_requires_output_path(self, theme):
        """file 模式未传 output_path 应抛 ValueError, 不静默退化."""
        with pytest.raises(ValueError, match="output_path"):
            prompt_assembler.assemble_stage3_prompt(theme, mode="file")

    def test_unknown_mode_raises(self, theme):
        """未知 mode 应抛 ValueError, 防 typo 误用."""
        with pytest.raises(ValueError, match="unknown mode"):
            prompt_assembler.assemble_stage3_prompt(theme, mode="bogus")
