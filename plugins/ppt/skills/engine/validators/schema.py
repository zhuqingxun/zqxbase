"""variant schema 校验器 (S4 Phase 2 从 validate_plan.py 拆出)。

按 visual_type 路由到 schemas/variants.py 对应 Content 子模型做严格校验 (extra='forbid')。
"""
from __future__ import annotations

from engine.validators.types import SlideResult


# ---------------------------------------------------------------------------
# variant 子模型查找
# ---------------------------------------------------------------------------

_VARIANT_MODEL_CACHE: dict[str, type] | None = None


def _lookup_variant_model(visual_type: str) -> type:
    """按 visual_type 返回 schemas/variants.py 对应 Content 子模型类。

    首次调用时构建缓存；未找到抛 KeyError。
    """
    global _VARIANT_MODEL_CACHE
    if _VARIANT_MODEL_CACHE is None:
        from schemas import variants as _v  # 延迟导入避免循环
        cache: dict[str, type] = {}
        import inspect
        from pydantic import BaseModel
        for _name, _cls in inspect.getmembers(_v, inspect.isclass):
            if not issubclass(_cls, BaseModel) or _cls is BaseModel:
                continue
            vt_field = _cls.model_fields.get("visual_type")
            if vt_field is None:
                continue
            # Literal[...] 的取值位于 annotation 的 __args__
            anno = vt_field.annotation
            args = getattr(anno, "__args__", ())
            for literal_val in args:
                if isinstance(literal_val, str):
                    cache[literal_val] = _cls
        _VARIANT_MODEL_CACHE = cache
    return _VARIANT_MODEL_CACHE[visual_type]


# ---------------------------------------------------------------------------
# variant 校验 (从 validate_slide 的 group=='variant' 分支抽出)
# ---------------------------------------------------------------------------

def validate_variant_schema(slide: dict, result: SlideResult, visual_type: str, content: dict) -> SlideResult:
    """variant 类型按 schemas/variants.py 子模型严格校验。mutate + return result。"""
    try:
        model_cls = _lookup_variant_model(visual_type)
    except KeyError:
        result.status = "FAIL"
        result.total_issue = f"visual_type '{visual_type}' 未注册 variant 子模型"
        return result

    variant_data = slide.get("variant")
    if variant_data is None:
        # 路径 B 拦截（ARCH-002 阶段1）：variant 类型必须把专属字段放进
        # slide['variant']（path X）。缺 variant 块 = 平铺到 content 顶层
        # （path Y），违反数据契约，不再默默兜底 PASS，直接 FAIL。
        # 注：阶段1 validate 严于 renderer（renderer 仍双查 path X/Y）是
        # 有意的防御纵深，阶段2/3（S4）才收口 renderer 兜底，非 bug。
        declared_fields = set(model_cls.model_fields.keys()) - {"visual_type"}
        flattened = sorted(declared_fields & set(content.keys()))
        result.status = "FAIL"
        result.total_issue = (
            f"slide {result.slide_id} ({visual_type}): 变体专属字段须放 slide.variant "
            f"(path X)，当前缺 variant 块"
            + (f"，content 顶层平铺了: {flattened}" if flattened else "")
        )
        return result

    # 路径 A：slide['variant'] 已提供（推荐路径）
    payload = dict(variant_data)
    payload.setdefault("visual_type", visual_type)
    try:
        model_cls.model_validate(payload)
        result.status = "PASS"
    except Exception as exc:
        result.status = "FAIL"
        result.total_issue = (
            f"variant 按 {model_cls.__name__} 校验失败: {exc.__class__.__name__}"
        )
    return result

