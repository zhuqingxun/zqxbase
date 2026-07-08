"""Pytest 根配置：把 plugins/ppt/ 加入 sys.path，让 `from schemas.*` / `from engine.*` 可解析。

PEP 723 / uv run pytest 场景下，tests 目录与 schemas/engine 同级，pytest 默认不把父目录加入 path。
"""
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
