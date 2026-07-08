# Baseline: us-military-rotation E2E fixture

本文件是 us-military-rotation deck 的人工质量基准, 供回归对照参考 (非机器断言, 机器断言见 `expected/assertions.yaml`).

## 来源

- 课题: 美军陆军军官轮岗制度 -> 企业干部流动机制的组织设计研究.
- recorded 产物来自一次真实 ppt:create 运行 (v6), 用户确认满意, 5/31 经 ppt:taste 视觉选型评审收敛.
- 全部素材已按 K01-K22 脱敏 (脱敏映射见 `fixture-manifest.yaml`).

## 质量基准 (人工确认要点)

1. **结构完整**: 19 页, 封面 -> 目录 -> KPI 概览 -> 三层痛点 -> 五大洞察 -> 落地路径 -> 风险 -> 致谢, 叙事弧线闭环.
2. **版式多样**: 命中 18 个 huawei 专属版式中的多种 (cover-left-bar / kpi-stats / governance / pyramid / process-flow-huawei / architecture-layered / matrix-2x2 / timeline-huawei / cards-6 / heatmap-matrix / roadmap / risk-list / thankyou), 应用率 100%.
3. **内容量达标**: 全部 19 页过 validate_plan 内容量门禁 (0 FAIL), 每页要点充实有数据/案例支撑.
4. **布局多样性**: 无连续两页同 visual_type 反模式 (section-divider-dark 作为章节分隔多次出现属正常结构性复用).

## 回归用途

renderer 重构 / god module 拆分后, 用 `orchestrator replay input --fixture <本目录>` 回放, 比对:
- slide 数 == 19
- 每页 visual_type 序列与 `expected/assertions.yaml` 一致
- 每页 shape 数 + 可见文本列表两次 replay 结构等价 (确定性)

产物结构变化即视为回归, 须人工复核是否预期.
