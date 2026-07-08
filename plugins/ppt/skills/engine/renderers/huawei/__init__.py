"""华为主题 renderer 包 (S4 Phase 1): import 全部 18 子模块触发 @register_renderer 注册。

每个子模块对应一个 visual_type; helper 单一来源在 engine.renderer_kit。
"""
from engine.renderers.huawei import (  # noqa: F401
    cover_left_bar,
    toc,
    section_divider_dark,
    kpi_stats,
    matrix_2x2,
    architecture_layered,
    timeline_huawei,
    process_flow_huawei,
    swot,
    roadmap,
    pyramid,
    heatmap_matrix,
    thankyou,
    cards_6,
    rings,
    personas,
    risk_list,
    governance,
)
