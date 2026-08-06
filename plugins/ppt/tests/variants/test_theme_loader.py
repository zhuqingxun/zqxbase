# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0", "pyyaml>=6.0"]
# ///
"""SPEC-TL-*：Theme loader 四场景 + _REMOVED_THEMES 常量契约。

依赖：Dev T1（load_theme 重写）+ T2（tokens.yaml / layouts.yaml 就绪）。
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytest.importorskip("yaml", reason="pyyaml required")

try:
    from engine.render import load_theme, _REMOVED_THEMES, _DEFAULT_THEME  # type: ignore
except ImportError:
    load_theme = None  # type: ignore
    _REMOVED_THEMES = None  # type: ignore
    _DEFAULT_THEME = None  # type: ignore

pytestmark = pytest.mark.skipif(
    load_theme is None or _REMOVED_THEMES is None,
    reason="engine.render.load_theme / _REMOVED_THEMES 尚未实现（Dev T1 前）",
)

HUAWEI_DIR_EXISTS = (Path(__file__).resolve().parents[2] / "themes" / "huawei").is_dir()


# ============================================================
# 常量契约（SPEC-TL-12）
# ============================================================

def test_removed_themes_exact_set():
    """SPEC-TL-12：`_REMOVED_THEMES` 必须精确等于三项集合。"""
    assert _REMOVED_THEMES == {"clean-light", "academic", "dark-business"}


def test_default_theme_is_huawei():
    """Plan T1：`_DEFAULT_THEME = 'huawei'`。"""
    assert _DEFAULT_THEME == "huawei"


# ============================================================
# 四场景（对齐 PRD §7.3.1）
# ============================================================

@pytest.mark.skipif(not HUAWEI_DIR_EXISTS, reason="themes/huawei/ 尚未就绪（Dev T2 前）")
def test_load_theme_huawei_returns_tokens(tmp_path):
    """SPEC-TL-1：`load_theme('huawei')` 返回含必需 token 的 dict。"""
    result = load_theme("huawei")
    assert isinstance(result, dict)
    colors = result.get("colors") or result.get("tokens", {}).get("colors")
    assert colors.get("primary") == "#C7000B"


@pytest.mark.skipif(not HUAWEI_DIR_EXISTS, reason="themes/huawei/ 尚未就绪（Dev T2 前）")
def test_load_theme_none_defaults_to_huawei(caplog):
    """SPEC-TL-2 / TL-11：`load_theme(None)` → huawei + INFO 日志。"""
    caplog.set_level(logging.INFO)
    result = load_theme(None)
    assert isinstance(result, dict)
    # INFO 日志含 defaulting / huawei 提示
    msgs = " ".join(rec.message.lower() for rec in caplog.records)
    assert "default" in msgs or "huawei" in msgs


@pytest.mark.parametrize("removed", ["clean-light", "academic", "dark-business"])
def test_load_theme_removed_raises_valueerror(removed):
    """SPEC-TL-3/4/5：已删除主题 → `ValueError`，信息含 'was removed' + 'huawei'。"""
    with pytest.raises(ValueError) as excinfo:
        load_theme(removed)
    msg = str(excinfo.value)
    assert "was removed" in msg
    assert "huawei" in msg.lower()


@pytest.mark.parametrize("unknown", ["foo-bar", "huwei", "academic-v2"])
def test_load_theme_unknown_raises_filenotfound(unknown):
    """SPEC-TL-6 / TL-7：未知主题（非 removed 清单）→ `FileNotFoundError`。"""
    # O4 决策：Plan T1 选 FileNotFoundError for 未知目录
    with pytest.raises(FileNotFoundError) as excinfo:
        load_theme(unknown)
    msg = str(excinfo.value)
    assert "not found" in msg.lower()
    assert "available" in msg.lower() or "huawei" in msg.lower()


# ============================================================
# O7：双暴露字典结构（扁平 + 嵌套）
# ============================================================

@pytest.mark.skipif(not HUAWEI_DIR_EXISTS, reason="themes/huawei/ 尚未就绪（Dev T2 前）")
def test_load_theme_exposes_both_flat_and_nested():
    """Plan T1：返回 dict 同时暴露 `tokens` 嵌套 key + tokens 顶层扁平 key。

    旧 25 renderer 读 `theme['colors']`；新 renderer 读 `theme['tokens']['colors']`。
    `_layouts` 作为独立 key 给新 renderer 读 layouts.yaml。
    """
    result = load_theme("huawei")
    # 扁平（旧 renderer 兼容路径）
    assert "colors" in result
    assert result["colors"].get("primary") == "#C7000B"
    # 嵌套（新 renderer 路径）
    assert "tokens" in result
    assert result["tokens"].get("colors", {}).get("primary") == "#C7000B"
    # layouts 暴露
    assert "_layouts" in result or "layouts" in result


# ============================================================
# SPEC-TL-8：旧单文件 huawei.yaml 不读
# ============================================================

def test_legacy_single_file_huawei_yaml_removed():
    """SPEC-RG-4 / SPEC-TL-8：`themes/huawei.yaml`（单文件）必须不存在（Dev T4 删除）。"""
    legacy = Path(__file__).resolve().parents[2] / "themes" / "huawei.yaml"
    assert not legacy.exists(), f"旧单文件 {legacy} 仍存在，Dev T4 未完成"
