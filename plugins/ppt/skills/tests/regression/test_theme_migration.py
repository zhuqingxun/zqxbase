# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pydantic>=2.0"]
# ///
"""SPEC-RG-*：旧主题破坏性删除 + PlanMeta 默认值变更的回归断言。

测试策略：仅检查静态磁盘状态与源码常量，Dev T1/T4 完成即可生效，不依赖 renderer。

对应规格：
- SPEC-RG-1/2/3：academic / clean-light / dark-business yaml 不存在
- SPEC-RG-4：huawei.yaml 单文件不存在
- SPEC-RG-5：palettes.yaml 不存在
- SPEC-RG-6：themes/ 下仅 huawei 子目录
- SPEC-RG-8：PlanMeta 默认 theme == "huawei"
- SPEC-RG-9：render.py 源码中 'clean-light' 只出现在 _REMOVED_THEMES 常量内
"""
from __future__ import annotations

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
THEMES_DIR = PLUGIN_ROOT / "themes"
RENDER_PY = PLUGIN_ROOT / "engine" / "render.py"
SLIDE_PLAN_PY = PLUGIN_ROOT / "schemas" / "slide_plan.py"


# ============================================================
# 旧主题 yaml 不存在（SPEC-RG-1..5）
# ============================================================

@pytest.mark.parametrize(
    "filename",
    ["academic.yaml", "clean-light.yaml", "dark-business.yaml", "huawei.yaml", "palettes.yaml"],
    ids=["RG-1-academic", "RG-2-clean-light", "RG-3-dark-business", "RG-4-huawei-single", "RG-5-palettes"],
)
def test_legacy_theme_file_removed(filename):
    """SPEC-RG-1/2/3/4/5：旧主题/palettes yaml 必须被删除。"""
    path = THEMES_DIR / filename
    assert not path.exists(), f"旧文件 {path} 仍存在（Dev T4 未删除）"


# ============================================================
# themes/ 目录仅含 huawei（SPEC-RG-6）
# ============================================================

def test_themes_directory_contains_only_huawei():
    """SPEC-RG-6：themes/ 下仅 huawei/ 子目录（允许 .gitkeep）。"""
    assert THEMES_DIR.is_dir(), f"themes 目录缺失: {THEMES_DIR}"
    entries = [e for e in THEMES_DIR.iterdir() if e.name != ".gitkeep"]
    dirs = [e.name for e in entries if e.is_dir()]
    files = [e.name for e in entries if e.is_file()]
    assert dirs == ["huawei"], f"themes/ 子目录不仅 huawei: {dirs}"
    assert files == [], f"themes/ 顶层不应有文件（除 .gitkeep）: {files}"


# ============================================================
# PlanMeta 默认 theme 变更（SPEC-RG-8 / SPEC-PM-1）
# ============================================================

def test_plan_meta_default_theme_is_huawei():
    """SPEC-RG-8 / SPEC-PM-1：PlanMeta(title="X") 未传 theme 时，theme 字段默认 "huawei"。

    Dev-2 任务：把 schemas/slide_plan.py:36 的 `theme: str = "clean-light"` 改为 "huawei"。
    """
    from schemas.slide_plan import PlanMeta

    meta = PlanMeta(title="X")
    assert meta.theme == "huawei", (
        f"PlanMeta.theme 默认应为 'huawei'，实际 {meta.theme!r}。"
        f"Dev-2 需修改 schemas/slide_plan.py 的 theme 默认值"
    )


def test_plan_meta_explicit_huawei():
    """SPEC-PM-2：显式传 theme='huawei' 合法。"""
    from schemas.slide_plan import PlanMeta

    meta = PlanMeta(title="X", theme="huawei")
    assert meta.theme == "huawei"


def test_plan_meta_removed_theme_not_rejected_here():
    """SPEC-PM-3：PlanMeta 对 'clean-light' 等 removed 主题不拒绝（由 load_theme 统一处理）。

    这是架构决策：PlanMeta 只管 str 字段类型，主题合法性检查下沉到 load_theme。
    """
    from schemas.slide_plan import PlanMeta

    meta = PlanMeta(title="X", theme="clean-light")  # 不抛 ValidationError
    assert meta.theme == "clean-light"


# ============================================================
# render.py 源码断言（SPEC-RG-9 / SPEC-TL-12 / SPEC-TL-13）
# ============================================================

@pytest.fixture(scope="module")
def render_source() -> str:
    if not RENDER_PY.exists():
        pytest.skip(f"{RENDER_PY} 不存在（Dev T1 前）")
    return RENDER_PY.read_text(encoding="utf-8")


def test_removed_themes_constant_defined(render_source):
    """SPEC-TL-12：render.py 定义 `_REMOVED_THEMES` 常量并精确含三个已删除主题名。"""
    assert "_REMOVED_THEMES" in render_source, "render.py 缺少 _REMOVED_THEMES 常量"
    for removed in ("clean-light", "academic", "dark-business"):
        assert removed in render_source, f"_REMOVED_THEMES 未包含 {removed!r}"


def test_default_theme_constant_is_huawei(render_source):
    """Plan T1：render.py 的 _DEFAULT_THEME == "huawei"。"""
    assert "_DEFAULT_THEME" in render_source
    # 简单断言：'_DEFAULT_THEME' 附近出现 '"huawei"' 或 "'huawei'"
    import re
    m = re.search(r"_DEFAULT_THEME\s*[:=]\s*[^\n]*huawei", render_source)
    assert m, "_DEFAULT_THEME 定义未指向 'huawei'"


def test_no_clean_light_as_default_value(render_source):
    """SPEC-RG-9：`clean-light` 字符串仅能出现在 _REMOVED_THEMES 上下文，不能作为 default 值。

    启发式：所有 'clean-light' 命中必须在 _REMOVED_THEMES 或相关注释/错误消息里出现，
    不能出现在 `default="clean-light"` 或 `theme = "clean-light"` 这类赋值右侧。
    """
    import re
    # 禁止模式：等号直接赋值 clean-light 作为默认
    forbidden_patterns = [
        r'default\s*=\s*["\']clean-light["\']',
        r'theme\s*:\s*str\s*=\s*["\']clean-light["\']',
        r'theme\s*=\s*["\']clean-light["\']',
    ]
    for pat in forbidden_patterns:
        m = re.search(pat, render_source)
        assert not m, f"render.py 含禁止的 default 模式 {pat!r}（SPEC-RG-9 违规）: {m.group(0) if m else ''}"


def test_load_theme_order_removed_before_dir_check(render_source):
    """SPEC-TL-13：load_theme 必须先检查 _REMOVED_THEMES，再检查目录存在。

    启发式：在 load_theme 函数体内，`_REMOVED_THEMES` 出现位置 < `is_dir(` 或 `FileNotFoundError` 首次出现位置。
    """
    # 定位 load_theme 函数开头
    idx = render_source.find("def load_theme(")
    assert idx >= 0, "render.py 无 load_theme 函数定义"
    # 截取函数体（下一个 def 之前）
    next_def = render_source.find("\ndef ", idx + 1)
    body = render_source[idx: next_def if next_def > 0 else len(render_source)]

    # 跳过 docstring（docstring 可能引用 FileNotFoundError / _REMOVED_THEMES 作为行为说明）
    # 寻找第一个 if 语句作为函数体起点
    first_if = body.find("\n    if ")
    if first_if < 0:
        pytest.skip("load_theme 函数体无 if 语句，无法断言顺序")
    code_body = body[first_if:]

    # "if name in _REMOVED_THEMES" 必须早于 "is_dir(" 检查
    import re
    removed_guard = re.search(r"if\s+name\s+in\s+_REMOVED_THEMES", code_body)
    dir_guard = re.search(r"is_dir\(", code_body)
    assert removed_guard is not None, "load_theme 函数体缺少 `if name in _REMOVED_THEMES` 守卫"
    if dir_guard is not None:
        assert removed_guard.start() < dir_guard.start(), (
            f"load_theme 中 _REMOVED_THEMES 守卫位置 ({removed_guard.start()}) "
            f"必须早于 is_dir 检查 ({dir_guard.start()})；顺序颠倒会让 FileNotFoundError 覆盖 removed 消息"
        )


# ============================================================
# 发布阶段 regression（SPEC-RG-7/10）跳过守护
# ============================================================

LEGACY_FIXTURE = PLUGIN_ROOT / "tests" / "fixtures" / "legacy-slides.yaml"


@pytest.mark.skipif(not LEGACY_FIXTURE.exists(), reason="legacy-slides.yaml 未就绪（Dev T5 前）")
def test_legacy_plan_renders_with_huawei_theme(tmp_path):
    """SPEC-RG-7：用 legacy-slides.yaml（含 bullets / cards-3 / framework 等旧 visual_type）
    + theme=huawei 渲染成功，证明旧 25 renderer 对新目录主题无感知。
    """
    import yaml as _yaml
    from engine.render import render_presentation, load_theme  # noqa: F401
    from schemas.slide_plan import SlidePlan

    data = _yaml.safe_load(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    plan = SlidePlan.model_validate(data)
    theme = load_theme("huawei")
    out = tmp_path / "legacy.pptx"
    render_presentation(plan, theme, str(out))
    assert out.exists() and out.stat().st_size > 0
