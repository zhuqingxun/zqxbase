# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""tests/security/ 路径下的脱敏模块入口——re-export 自 tests/pixel/assert_no_sensitive.py。

单一实现源在 tests/pixel/ 下（与 QA 的 test_desensitization.py 的 _SCANNER_PATH 对齐）。
本模块供 team-lead 约定的 tests/security/ 门禁路径 import 使用。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_IMPL_PATH = Path(__file__).resolve().parents[1] / "pixel" / "assert_no_sensitive.py"
_spec = importlib.util.spec_from_file_location("_ans_impl", _IMPL_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

RULES = _mod.RULES
DEFAULT_WHITELIST = _mod.DEFAULT_WHITELIST
TEXT_EXTENSIONS = _mod.TEXT_EXTENSIONS
Rule = _mod.Rule
Hit = _mod.Hit
assert_no_sensitive = _mod.assert_no_sensitive
scan = _mod.scan
