# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.0", "pyyaml>=6.0"]
# ///
"""prompt_assembler.py: schema-to-prompt 派生器 (Q4 决议).

运行时从 schemas/variants.py 的 VariantUnion 派生 18 版式字段说明,
并叠加 theme.preferences (硬约束/软引导/退回链) 拼成 Stage 3 prompt 注入文本.

设计硬约束 (Leader 指引 #1, research §1.3):
- 必须用 Pydantic V2 model_json_schema(), 禁止自研 model_fields 递归
- model_json_schema() 已规范化处理嵌套 $defs / minItems / maxItems / Literal const /
  extra='forbid' (Annotated[..., Field(min_length=...)] 等), research §1.2 已实测
  覆盖 KpiStats / ArchitectureLayered / HeatmapMatrix 三种代表性嵌套

输出契约:
- assemble_stage3_prompt(theme, mode='embed') -> str (markdown)
- assemble_stage3_prompt(theme, mode='file') -> str (写到 .theme-prompt.md, 返回路径)

CLI 入口 (P7 SKILL.md 调用):
    uv run --script engine/prompt_assembler.py --theme huawei --output /path/to/.theme-prompt.md
"""

from __future__ import annotations

import argparse
import logging
import sys
import typing
from pathlib import Path
from typing import Any

# 当作 PEP 723 单脚本运行 (`uv run --script`) 时, CWD 不在 sys.path,
# 兄弟模块 import (engine.theme_loader / schemas.variants) 会失败。
# 既有 engine/render.py / plan.py 用同 pattern: 把 plugin 根目录推入 sys.path。
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

logger = logging.getLogger(__name__)


# =====================================================================
# 1. variant 类发现 (research §1.3)
# =====================================================================


def _iter_variant_classes() -> list[type]:
    """从 schemas.variants.VariantUnion 拿 18 个 Content 类.

    VariantUnion = Annotated[Union[Cls1, Cls2, ...], Field(discriminator=...)]
    typing.get_args(VariantUnion) -> (Union[Cls1, ...], FieldInfo(...))
    取索引 [0] 拿 Union, .__args__ 拿 tuple of classes.
    """
    from schemas.variants import VariantUnion  # noqa: PLC0415

    union_args = typing.get_args(VariantUnion)[0].__args__
    return list(union_args)


def _visual_type_of(cls: type) -> str:
    """从 Content 类的 visual_type Literal 提取字符串值."""
    vt_field = cls.model_fields.get("visual_type")
    if vt_field is None:
        return cls.__name__
    args = getattr(vt_field.annotation, "__args__", ())
    for a in args:
        if isinstance(a, str):
            return a
    return cls.__name__


# =====================================================================
# 2. schema 派生 (research §1.2 实证用 model_json_schema())
# =====================================================================


def _schema_for(cls: type) -> dict[str, Any]:
    """派生器入口: 直接用 Pydantic V2 内置 model_json_schema().

    禁止用 model_fields 自研递归 (Leader 指引 #1) — 内置已规范化处理:
    - 嵌套子模型自动放入 $defs
    - Field(min_length, max_length) -> minItems / maxItems
    - Literal['x'] -> {const: 'x'}
    - extra='forbid' -> additionalProperties: false
    """
    return cls.model_json_schema()


def derive_variant_field_specs() -> dict[str, dict[str, Any]]:
    """从 schemas/variants.py 的 VariantUnion 派生 18 版式字段规格.

    Returns:
      {
        'kpi-stats': {
            'class_name': 'KpiStatsContent',
            'schema': {...},          # 完整 JSON Schema
            'required': ['title', 'kpis'],   # 不含 visual_type
            'properties': {...},      # 顶层 properties (不含 visual_type)
            'defs': {...},            # $defs 嵌套子模型
        },
        ...
      }
    """
    specs: dict[str, dict[str, Any]] = {}
    for cls in _iter_variant_classes():
        vt = _visual_type_of(cls)
        schema = _schema_for(cls)
        properties = dict(schema.get("properties", {}))
        properties.pop("visual_type", None)
        required = [r for r in schema.get("required", []) if r != "visual_type"]
        specs[vt] = {
            "class_name": cls.__name__,
            "schema": schema,
            "required": required,
            "properties": properties,
            "defs": dict(schema.get("$defs", {})),
        }
    return specs


# =====================================================================
# 3. cookbook 渲染: schema -> markdown
# =====================================================================


def _render_field_constraints(prop: dict[str, Any]) -> str:
    """单个 property 的简短约束摘要."""
    parts: list[str] = []
    typ = prop.get("type")
    if typ == "array":
        items = prop.get("items", {})
        item_ref = items.get("$ref")
        if item_ref:
            ref_name = item_ref.rsplit("/", 1)[-1]
            parts.append(f"list of {ref_name}")
        elif "type" in items:
            parts.append(f"list of {items['type']}")
        if "minItems" in prop or "maxItems" in prop:
            mn = prop.get("minItems", "")
            mx = prop.get("maxItems", "")
            parts.append(f"({mn}..{mx})")
    elif "$ref" in prop:
        parts.append(prop["$ref"].rsplit("/", 1)[-1])
    elif "anyOf" in prop:
        sub_types = []
        for sub in prop["anyOf"]:
            if sub.get("type") == "null":
                continue
            if "type" in sub:
                sub_types.append(sub["type"])
            elif "$ref" in sub:
                sub_types.append(sub["$ref"].rsplit("/", 1)[-1])
        parts.append(f"{' | '.join(sub_types) or 'any'}?")
    elif "const" in prop:
        parts.append(f"const={prop['const']!r}")
    elif "enum" in prop:
        parts.append(f"enum={prop['enum']}")
    elif typ:
        parts.append(typ)
    if "minimum" in prop or "maximum" in prop:
        parts.append(f"range[{prop.get('minimum','')}, {prop.get('maximum','')}]")
    return " ".join(parts) or "any"


def _render_def(def_name: str, def_schema: dict[str, Any]) -> list[str]:
    """渲染单个 $def 子模型的字段列表."""
    lines: list[str] = [f"  {def_name}:"]
    props = def_schema.get("properties", {})
    required = set(def_schema.get("required", []))
    for fname, fschema in props.items():
        flag = "*" if fname in required else " "
        lines.append(f"    {flag} {fname}: {_render_field_constraints(fschema)}")
    return lines


def derive_field_cookbook(specs: dict[str, dict[str, Any]]) -> str:
    """把 derive_variant_field_specs 输出渲染成 prompt 可读 markdown.

    紧凑约定 (压缩 prompt token):
    - 字段前 `*` = required, 无标记 = optional
    - 类型后 `?` = nullable (Pydantic anyOf [type, null])
    - 列表约束 `(N..M)` = minItems..maxItems
    - 嵌套子模型直接缩进展开, 不另起 'defs:' 标签
    """
    lines: list[str] = [
        "## 母版字段速查 (派生自 schemas/variants.py)",
        "",
        "> `*`=required, 类型后 `?`=nullable, `(N..M)`=列表 minItems..maxItems",
        "",
    ]
    # 共享子模型去重: 多个母版引用同一 $def (如自适应 cards/process/comparison
    # 均含 AdaptivePoint) 时只渲染一次, 避免重复占用 prompt 预算。
    rendered_defs: set[str] = set()
    for vt in sorted(specs.keys()):
        spec = specs[vt]
        lines.append(f"### {vt} ({spec['class_name']})")
        required_set = set(spec["required"])
        for fname, fschema in spec["properties"].items():
            flag = "*" if fname in required_set else " "
            lines.append(f"  {flag} {fname}: {_render_field_constraints(fschema)}")
        for def_name, def_schema in spec["defs"].items():
            if def_name in rendered_defs:
                continue
            rendered_defs.add(def_name)
            lines.extend(_render_def(def_name, def_schema))
        lines.append("")
    return "\n".join(lines)


# =====================================================================
# 4. 决策框架: theme.preferences -> markdown
# =====================================================================


def _render_required_for_role(rules: dict[str, str]) -> list[str]:
    if not rules:
        return []
    lines = ["**角色映射 (硬约束)**: 当 slide.role 命中以下角色, 必须选指定 visual_type:"]
    # toc 启发式 (research §3.4 / plan §3.3 C: SlideRole 无 toc 枚举)
    for role, vt in rules.items():
        if role == "toc":
            lines.append(
                f"- 当 slide 内容为目录页 (content.title 形如 \"目录\"/\"Contents\"/"
                f"\"Table of Contents\", 或包含 编号+章节名+页码 三件套) -> 必须选 {vt}"
            )
        else:
            lines.append(f"- role={role!r} -> 必须选 {vt}, 不允许选其他")
    return lines


def _render_required_for_content(rules: list[dict]) -> list[str]:
    if not rules:
        return []
    lines = ["**内容触发 (硬约束)**: 当 slide 内容满足以下条件, 必须选指定 visual_type:"]
    for r in rules:
        trigger = r.get("trigger", "?")
        vt = r.get("visual_type", "?")
        desc = r.get("description", "")
        suffix = f" — {desc}" if desc else ""
        lines.append(f"- 触发 `{trigger}` -> 必须选 {vt}{suffix}")
    return lines


def _render_forbidden(forbidden: list[str]) -> list[str]:
    if not forbidden:
        return []
    lines = ["**禁用版式 (硬约束)**: 主题禁止以下 visual_type, 应选其他替代:"]
    lines.append(f"- {', '.join(forbidden)}")
    return lines


def _render_visual_type_preferences(prefs: dict[str, float]) -> list[str]:
    if not prefs:
        return []
    lines = [
        "**软引导 (visual_type 偏好权重 0..1)**: 内容歧义时按权重排序, 高权重优先:",
    ]
    sorted_prefs = sorted(prefs.items(), key=lambda kv: -float(kv[1]))
    for vt, w in sorted_prefs:
        lines.append(f"- {vt} ({w})")
    return lines


def _render_fallback_chain(chain: dict[str, list[str]]) -> list[str]:
    if not chain:
        return []
    lines = ["**退回链 (schema 校验失败时的 fallback 顺序)**:"]
    for vt, fallbacks in chain.items():
        path = " -> ".join([vt, *fallbacks])
        lines.append(f"- {path}")
    return lines


def derive_decision_block(theme: dict[str, Any]) -> str:
    """从 theme.preferences 拼接决策框架 markdown 段.

    包含: 6 类硬约束 (required_for_role / required_for_content / forbidden) +
    12 类软引导 (visual_type_preferences) + fallback_chain.

    theme.preferences 缺失或为空时, 返回兜底说明 (LLM 走通用 fallback 决策树).
    """
    prefs = theme.get("preferences") or {}
    if not isinstance(prefs, dict) or not prefs:
        return (
            "## 主题决策框架\n\n"
            "(主题未提供 preferences.yaml, LLM 应使用通用 visual_type 决策树.)\n"
        )

    lines: list[str] = ["## 主题决策框架 (自 themes/<theme>/preferences.yaml)", ""]

    lines.append("### 硬约束 (必须遵守)")
    lines.append("")
    lines.extend(_render_required_for_role(prefs.get("required_for_role", {})))
    lines.append("")
    lines.extend(_render_required_for_content(prefs.get("required_for_content", [])))
    lines.append("")
    lines.extend(_render_forbidden(prefs.get("forbidden_visual_types", [])))
    lines.append("")

    vp = prefs.get("visual_type_preferences", {}) or {}
    if vp:
        lines.append("### 软引导 (按权重排序)")
        lines.append("")
        lines.extend(_render_visual_type_preferences(vp))
        lines.append("")

    fc = prefs.get("fallback_chain", {}) or {}
    if fc:
        lines.append("### 退回链")
        lines.append("")
        lines.extend(_render_fallback_chain(fc))
        lines.append("")

    return "\n".join(lines)


# =====================================================================
# 5. 字段路径提示 (path X 决议, research §2.3)
# =====================================================================


_PATH_X_HINT = """## 字段填法 (path X 决议)

huawei 18 版式的字段必须按以下两层放置:

- **公共字段 (放 slide.content 下)**: title, subtitle, description, body_text, key_points, ...
- **变体专属字段 (放 slide.variant 下)**: kpis, layers, steps, phases, quadrants,
  rings, personas, risks, units, items, lanes, levels, rows, columns, top_box, ...

示例 (kpi-stats):
```yaml
slides:
  - id: 5
    visual_type: kpi-stats
    content:
      title: "..."           # 公共
      subtitle: "..."        # 公共
    variant:
      kpis:                  # 专属字段, 放 variant 下
        - {label: "...", value: "..."}
```

**禁止**把变体专属字段平铺到 slide.content 顶层 (虽然兜底仍工作, 但 schema 严格化将失败).
"""


def derive_path_x_hint() -> str:
    """字段路径硬约束 (research §2.3 决议: 用 variant 路径, 不用 content extra)."""
    return _PATH_X_HINT


# =====================================================================
# 6. 总装配
# =====================================================================


def assemble_stage3_prompt(
    theme: dict[str, Any], mode: str = "embed", output_path: str | Path | None = None
) -> str:
    """组装 Stage 3 完整决策框架 prompt 文本.

    Args:
      theme: load_theme() 返回的 dict (期望含 'preferences' key, 缺失时输出兜底)
      mode:
        - 'embed': 返回完整 markdown 字符串
        - 'file' : 把内容写到 output_path, 返回路径字符串

    Returns:
      mode='embed' 时返回 markdown; mode='file' 时返回写出的文件路径.
    """
    decision = derive_decision_block(theme)
    specs = derive_variant_field_specs()
    cookbook = derive_field_cookbook(specs)
    path_hint = derive_path_x_hint()

    full = "\n".join([decision, path_hint, cookbook])

    if mode == "embed":
        return full
    if mode == "file":
        if output_path is None:
            raise ValueError("mode='file' requires output_path")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(full, encoding="utf-8")
        return str(out)
    raise ValueError(f"unknown mode={mode!r}, expected 'embed' or 'file'")


# =====================================================================
# 7. CLI 入口 (供 P7 skills/create/SKILL.md Stage 3 调用)
# =====================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成 Stage 3 决策框架 prompt (.theme-prompt.md)"
    )
    parser.add_argument("--theme", default="huawei", help="主题名称 (默认 huawei)")
    parser.add_argument(
        "--output",
        required=True,
        help="输出 .theme-prompt.md 路径 (workdir 下), Stage 3 LLM 通过 Read 加载",
    )
    args = parser.parse_args()

    # 优先用 theme_loader (P2 引入), fallback render.load_theme (兼容老路径)
    theme: dict | None = None
    try:
        from engine.theme_loader import load_theme as _load  # noqa: PLC0415
        theme = _load(args.theme)
    except Exception:
        try:
            from engine.render import load_theme as _load  # noqa: PLC0415
            theme = _load(args.theme)
        except Exception as exc:
            print(f"ERROR: cannot load theme {args.theme!r}: {exc}", file=sys.stderr)
            sys.exit(1)

    out_path = assemble_stage3_prompt(theme or {}, mode="file", output_path=args.output)
    print(f"Wrote Stage 3 decision prompt to: {out_path}")


if __name__ == "__main__":
    main()
