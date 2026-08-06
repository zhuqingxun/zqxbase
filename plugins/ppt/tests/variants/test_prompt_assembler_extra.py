"""prompt_assembler 增量测试 (dev-2 协作补缺 + Leader 派工指引 #1).

补缺点:
1. 派生器源码中 model_fields 仅在 ≤1 处使用 (Literal 提取),不允许自研递归遍历
   (Leader 派工 #1 强约束: 必须用 model_json_schema())
2. assemble_stage3_prompt(mode='file') 写 .theme-prompt.md 落盘
3. validate_plan._load_theme_thresholds 的 fallback 链
   (theme_loader 优先 -> render.load_theme fallback -> 默认 60/30)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
PROMPT_ASSEMBLER_PY = PLUGIN_ROOT / "engine" / "prompt_assembler.py"


# ============================================================
# 1. model_fields 仅 ≤1 处使用 (派生器走 model_json_schema)
# ============================================================

class TestNoModelFieldsRecursion:
    """Leader 派工 #1: prompt_assembler 必须用 model_json_schema(),不许自研 model_fields 递归."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        if not PROMPT_ASSEMBLER_PY.exists():
            pytest.skip(f"{PROMPT_ASSEMBLER_PY} 未就绪")
        return PROMPT_ASSEMBLER_PY.read_text(encoding="utf-8")

    def test_model_fields_used_at_most_once(self, source: str):
        """model_fields 在派生器源码中 ≤ 1 处 (Literal 取值是允许的唯一例外)."""
        # 排除注释/docstring 中的提及
        non_comment_lines = [
            line for line in source.split("\n")
            if "model_fields" in line and not line.strip().startswith("#")
        ]
        # 进一步排除 docstring 内容 (用三引号简单判定)
        in_docstring = False
        actual_uses = []
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # 单行 docstring 切换状态 (开+关同行的情况)
                triple_count = stripped.count('"""') + stripped.count("'''")
                if triple_count % 2 == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            if "model_fields" in line:
                actual_uses.append(line)

        assert len(actual_uses) <= 1, (
            f"派生器中 model_fields 出现 {len(actual_uses)} 次 (允许 ≤ 1, "
            f"仅用于 _visual_type_of 的 Literal 提取):\n"
            + "\n".join(f"  - {l.strip()}" for l in actual_uses)
        )

    def test_model_json_schema_is_primary_path(self, source: str):
        """派生器主路径必须调 model_json_schema()."""
        assert "model_json_schema" in source, (
            "prompt_assembler 必须用 model_json_schema() 作为主派生路径 "
            "(research §1 + Leader 派工 #1)"
        )

    def test_no_self_written_field_recursion_keywords(self, source: str):
        """不应出现自研字段递归的典型代码模式."""
        # 排除注释行
        code_lines = [
            line for line in source.split("\n")
            if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # __args__ 用于从 Literal 提取 visual_type 是允许的, 不在禁止之列
        # 真正禁止的是: 手动遍历 nested model_fields 拿子模型字段
        # 用 grep "for .* in .*\.model_fields" 查
        recursion_pattern = re.compile(
            r"for\s+\w+\s+in\s+\w+\.model_fields",
        )
        matches = recursion_pattern.findall(code)
        assert not matches, (
            f"检测到自研 model_fields 遍历模式: {matches} "
            "(Leader 派工 #1 禁止, 用 model_json_schema 的 $defs)"
        )


# ============================================================
# 2. assemble_stage3_prompt(mode='file') 落盘
# ============================================================

class TestAssembleStage3PromptFileMode:
    """AC-014/SKILL.md 集成依赖: file 模式产出 .theme-prompt.md."""

    @pytest.fixture
    def theme(self):
        try:
            from engine.render import load_theme  # type: ignore
            return load_theme("huawei")
        except Exception as e:
            pytest.skip(f"theme 加载失败: {e}")

    def test_file_mode_writes_markdown_to_output_path(self, tmp_path, theme):
        """mode='file' 把内容写到 output_path, 返回路径字符串."""
        try:
            from engine.prompt_assembler import assemble_stage3_prompt  # type: ignore
        except ImportError:
            pytest.skip("prompt_assembler 未就绪")

        out = tmp_path / "subdir" / ".theme-prompt.md"
        result = assemble_stage3_prompt(theme, mode="file", output_path=out)

        # 返回路径字符串 (str)
        assert isinstance(result, str)
        # 文件已落盘
        assert out.exists(), f"file 模式应写出 {out}"
        # 父目录自动创建 (Plan §3.4 行为)
        assert out.parent.is_dir()
        # 内容非空且与 embed 模式一致
        content = out.read_text(encoding="utf-8")
        assert len(content) > 0
        embed_content = assemble_stage3_prompt(theme, mode="embed")
        assert content == embed_content, "file 模式内容应与 embed 模式一致"

    def test_file_mode_requires_output_path(self, theme):
        """mode='file' 缺 output_path 应 raise ValueError."""
        try:
            from engine.prompt_assembler import assemble_stage3_prompt  # type: ignore
        except ImportError:
            pytest.skip("prompt_assembler 未就绪")

        with pytest.raises(ValueError, match="output_path"):
            assemble_stage3_prompt(theme, mode="file")

    def test_unknown_mode_raises_value_error(self, theme):
        """未知 mode 应 raise ValueError."""
        try:
            from engine.prompt_assembler import assemble_stage3_prompt  # type: ignore
        except ImportError:
            pytest.skip("prompt_assembler 未就绪")

        with pytest.raises(ValueError, match="mode"):
            assemble_stage3_prompt(theme, mode="invalid-mode-xyz")


# ============================================================
# 3. _load_theme_thresholds fallback 链
# ============================================================

class TestLoadThemeThresholdsFallbackChain:
    """validate_plan._load_theme_thresholds:
    theme_loader 优先 -> render.load_theme fallback -> 默认 60/30
    """

    def test_default_60_30_when_no_preferences(self, monkeypatch):
        """所有加载路径都失败时,返回默认 0.60 / 0.30."""
        try:
            from engine import validate_plan as vp  # type: ignore
        except ImportError:
            pytest.skip("validate_plan 未就绪")

        if not hasattr(vp, "_load_theme_thresholds"):
            pytest.skip("Dev P8 前 _load_theme_thresholds 不存在")

        # monkeypatch 让两条路径都抛异常
        def _bad_loader(name):
            raise RuntimeError("simulated load failure")

        # patch theme_loader 路径
        import sys
        fake_theme_loader = type(sys)("engine.theme_loader")
        fake_theme_loader.load_theme = _bad_loader  # type: ignore
        monkeypatch.setitem(sys.modules, "engine.theme_loader", fake_theme_loader)

        # patch render.load_theme 也失败
        try:
            from engine import render as render_mod
            monkeypatch.setattr(render_mod, "load_theme", _bad_loader)
        except ImportError:
            pass

        warn, fail = vp._load_theme_thresholds("nonexistent-theme")
        assert warn == 0.60
        assert fail == 0.30

    def test_thresholds_from_huawei_preferences(self):
        """huawei 主题加载后, 阈值来自 preferences.yaml.application_thresholds."""
        try:
            from engine import validate_plan as vp  # type: ignore
        except ImportError:
            pytest.skip("validate_plan 未就绪")

        if not hasattr(vp, "_load_theme_thresholds"):
            pytest.skip("Dev P8 前")

        prefs_yaml = PLUGIN_ROOT / "themes" / "huawei" / "preferences.yaml"
        if not prefs_yaml.exists():
            pytest.skip("preferences.yaml 未就绪 (Dev P1 前)")

        warn, fail = vp._load_theme_thresholds("huawei")
        # 来自 preferences.yaml 的阈值或默认值,均应在 (0, 1) 区间
        assert 0 < fail < warn < 1, (
            f"阈值非法: warn={warn} fail={fail}"
        )
        # huawei 主题预期值: warn=0.60, fail=0.30 (Plan §1.2 application_thresholds)
        assert warn == pytest.approx(0.60, abs=0.01)
        assert fail == pytest.approx(0.30, abs=0.01)

    def test_thresholds_fallback_to_render_load_theme(self, monkeypatch):
        """theme_loader 不可用时, fallback 到 render.load_theme."""
        try:
            from engine import validate_plan as vp  # type: ignore
        except ImportError:
            pytest.skip("validate_plan 未就绪")

        if not hasattr(vp, "_load_theme_thresholds"):
            pytest.skip("Dev P8 前")

        # 让 theme_loader 不可导入 (sys.modules 注入 None 触发 ImportError)
        import sys
        # 备份原 theme_loader (如有)
        saved = sys.modules.get("engine.theme_loader")
        sys.modules["engine.theme_loader"] = None  # type: ignore

        try:
            # 此时 _load_theme_thresholds 应走 render.load_theme fallback
            # huawei 主题真实存在, 应能拿到阈值 (来自 preferences.yaml 或默认)
            warn, fail = vp._load_theme_thresholds("huawei")
            assert 0 < fail < warn < 1
        finally:
            # 恢复 sys.modules
            if saved is not None:
                sys.modules["engine.theme_loader"] = saved
            else:
                sys.modules.pop("engine.theme_loader", None)
