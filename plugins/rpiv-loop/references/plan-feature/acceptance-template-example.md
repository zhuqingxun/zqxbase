# acceptance.yaml 最小可用示例（阶段 5.6）

> 由 `plan-feature/SKILL.md` 阶段 5.6 引用。字段规范权威定义见 SKILL.md 阶段 5.6；空白骨架模板见 `<rpiv-loop-root>/tools/acceptance_template.yaml`。根键统一用 `criteria:`，两份勿漂移。

**YAML 示例**（最小可用模板，复制后替换内容）：

```yaml
# rpiv/validation/<feature>/acceptance.yaml
# 由 plan-feature 阶段产出骨架；validate 阶段填 evidence/status；delivery-report 只读不改
feature: <feature-name>
prd: prd-<feature-name>
plan: plan-<feature-name>
criteria:
  - id: AC-001
    given: 用户已配置 dod.yaml 且首次进入 rpiv-loop 工作流
    when: 执行 /rpiv-loop:prime 命令
    then: ensure_project_dod.py 被调用，rpiv/dod.yaml 已存在则静默跳过
    verification_method: uv run pytest tests/test_ensure_project_dod.py::test_idempotent_on_second_run
    blocking: true
    evidence: ""
    status: ""
    notes: ""
  - id: AC-002
    given: acceptance.yaml 存在一条 blocking AC 且 status 为空
    when: 触发 Write delivery-report-<feature>.md
    then: PostToolUse hook 退出码 2，stderr 提示 "DoD gate 未通过"
    verification_method: bash tests/integration/test_hook_blocks_unverified.sh
    blocking: true
    evidence: ""
    status: ""
    notes: ""
  - id: AC-003
    given: 8 条 AC 全部 passed 且 evidence 非空
    when: 运行 uv run --no-project python <rpiv-loop-root>/tools/check_acceptance.py <feature>
    then: 退出码 0，stdout 含 "ALL PASS"
    verification_method: uv run --no-project python <rpiv-loop-root>/tools/check_acceptance.py <feature>
    blocking: true
    evidence: ""
    status: ""
    notes: ""
```
