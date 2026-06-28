# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""theme_loader.py: 主题加载单一来源 (Single Source of Truth).

历史上 load_theme 在 engine/render.py / engine/plan.py 各有一份实现, 行为不一致:
- render.py: 目录加载 (tokens + layouts)
- plan.py: 单文件路径 (THEMES_DIR / f"{name}.yaml") - huawei 升级目录后永远 ENOENT
本模块是统一实现, 加载 tokens + layouts + preferences 三件套, 替代上述两处。

行为契约 (与原 render.py:load_theme 等价 + preferences 扩展):
- name=None -> 默认 huawei (INFO 日志)
- name 在 _REMOVED_THEMES -> ValueError
- name 目录不存在 -> FileNotFoundError
- 有效主题 -> 读 tokens.yaml + layouts.yaml + preferences.yaml (可选)
- preferences.yaml 缺失 -> preferences=空字典 (旧主题兼容, 不报错)
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

# 与 engine/render.py 保持一致的常量
_REMOVED_THEMES: set[str] = {"clean-light", "academic", "dark-business"}
_DEFAULT_THEME: str = "huawei"

# 防 path traversal: theme name 必须是简单标识符
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@lru_cache(maxsize=8)
def _load_theme_yaml(name: str) -> dict:
    """实际读 3 个 yaml + 组装合并字典. @lru_cache 避免重复 IO.

    Caller load_theme 已做完 name 校验 (safe-name + removed + dir-exists), 此处假定 name 合法.
    单次 CLI 通常调 1-2 次, 但 plan/validate_plan/prompt_assembler 各处调时缓存命中.
    dev 编辑 yaml 后需重启 Python process 才生效 (lru_cache 标准 trade-off).
    """
    theme_dir = THEMES_DIR / name
    tokens = yaml.safe_load((theme_dir / "tokens.yaml").read_text(encoding="utf-8")) or {}
    layouts = yaml.safe_load((theme_dir / "layouts.yaml").read_text(encoding="utf-8")) or {}
    prefs_path = theme_dir / "preferences.yaml"
    preferences: dict = {}
    if prefs_path.exists():
        preferences = yaml.safe_load(prefs_path.read_text(encoding="utf-8")) or {}
    return {
        "tokens": tokens,
        "layouts": layouts,
        "preferences": preferences,
        **tokens,
        "_layouts": layouts,
    }


def load_theme(name: str | None) -> dict:
    """加载主题目录下的 tokens.yaml + layouts.yaml + preferences.yaml 合并字典。

    返回 dict 结构 (与 render.py 的旧实现保持向后兼容, 新增 preferences key):
    - tokens: 顶层 dict (colors / fonts / type_scale_px ...)
    - layouts: 18 版式像素几何
    - preferences: theme.preferences.yaml 内容 (required_for_role / forbidden_visual_types
      / visual_type_preferences / fallback_chain / application_thresholds 等)
    - 顶层扁平: tokens 键扁平挂顶层 (**tokens 展开), _layouts 同时挂一级 key

    顺序契约 (SPEC-TL-13): 先判 removed 再检目录, 顺序反了 FileNotFoundError 会盖掉
    removed 消息 (已被 tests/regression/test_theme_migration.py 断言)。
    """
    if name is None:
        logger.info("theme not specified, defaulting to '%s'", _DEFAULT_THEME)
        name = _DEFAULT_THEME
    if not _SAFE_NAME_RE.match(name):
        # 防 path traversal: 拒绝 ".." / 绝对路径 / 引号 / 任何非简单标识符的 name
        raise ValueError(
            f"Invalid theme name: {name!r}. Must match {_SAFE_NAME_RE.pattern}."
        )
    if name in _REMOVED_THEMES:
        raise ValueError(
            f"theme '{name}' was removed in huawei-theme-complete release. "
            f"Use 'huawei' (the only supported theme). See release notes."
        )
    theme_dir = THEMES_DIR / name
    if not theme_dir.is_dir():
        if THEMES_DIR.is_dir():
            available = sorted(p.name for p in THEMES_DIR.iterdir() if p.is_dir())
        else:
            available = []
        raise FileNotFoundError(
            f"theme '{name}' not found under themes/. Available: {available}"
        )
    return _load_theme_yaml(name)
