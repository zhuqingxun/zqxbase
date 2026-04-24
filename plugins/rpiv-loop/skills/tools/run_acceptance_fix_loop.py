#!/usr/bin/env python3
"""biubiubiu 模式下 Leader agent 的 AC 修复循环 runbook（伪代码文档）。

=============================================================================
本脚本不独立运行。Leader agent（Claude 层）按本文档的循环语义自己执行
"failing AC 识别 → SendMessage Dev 修复 → QA 重验 → recheck" 循环，直到
check_acceptance.py 退出码 0 或触发护栏（10 轮上限 / same-error-twice）。
=============================================================================

## 一、循环语义

在 biubiubiu 模式 `#### 门禁 3：实现完成` 阶段，所有子任务快速检查通过后：

  1. QA agent 运行完整测试套件 + 初步 code-review
  2. QA 运行 `uv run D:/CODE/plugins/rpiv-loop/tools/check_acceptance.py <feature>`
  3. 退出码 0 -> 跳过循环，进入交付步骤 6
  4. 退出码 1/2 -> 进入下述循环

## 二、伪代码循环

```
round = 0
last_failure_set = None  # 上一轮失败 AC id 集合

while round < 10:
    # 1. 重新获取失败清单（带 JSON 便于 parse）
    result = subprocess.run(
        ["uv", "run", "D:/CODE/plugins/rpiv-loop/tools/check_acceptance.py",
         feature, "--json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        break  # 全部 passed

    payload = json.loads(result.stdout)
    failures = payload["failures"]  # [{"id": "AC-003", "reason": "..."}]
    failure_ids = {f["id"] for f in failures}

    # 2. same-error-twice 护栏：两轮完全相同的 failure 集合 -> 提前 escalate
    if last_failure_set is not None and last_failure_set == failure_ids:
        AskUserQuestion(
            "AC 修复连续两轮相同失败（疑似卡死）",
            options=[
                "查看失败清单并手动介入",
                "强制继续循环",
                "放弃交付（交付报告标注 AC 未通过）",
            ],
        )
        break  # 等用户决策

    # 3. 分派修复任务：按 AC id 分配给对应 Dev
    for failure in failures:
        SendMessage(
            to="Dev-X",  # Leader 根据 AC 涉及模块选 Dev
            summary=f"修复 {failure['id']}",
            message=(
                f"修复 {failure['id']}: {failure['reason']}\n"
                f"参考 acceptance.yaml 中 then 字段的期望结果。\n"
                "完成后 SendMessage Leader 简短汇报。"
            ),
        )

    # 4. 等所有 Dev 完成修复（消息驱动，非 sleep）
    wait_all_dev_done()

    # 5. 通知 QA 重跑 verification_method 并更新 acceptance.yaml
    SendMessage(
        to="QA",
        summary="重验失败 AC",
        message=(
            f"重跑 {sorted(failure_ids)} 对应的 verification_method，"
            "更新 acceptance.yaml 的 evidence + status 字段。"
        ),
    )
    wait_qa_done()

    # 6. 记录本轮失败集合，进入下一轮
    last_failure_set = failure_ids
    round += 1

# 7. 10 轮上限触发
if round == 10:
    AskUserQuestion(
        "AC gate 10 轮未通过",
        options=[
            "继续再 10 轮",
            "查看失败清单并手动介入",
            "放弃交付（交付报告标注 AC 未通过）",
        ],
    )
```

## 三、护栏清单

- **10 轮上限**：避免无限消耗 context / API 额度
- **same-error-twice 提前 escalate**：连续两轮失败集合完全相同 -> 立即 AskUserQuestion，不等到 10 轮
- **Dev agent 无响应**：重启 agent 后轮次不重置（SendMessage 失败 / 超时视为无响应）
- **acceptance.yaml 被误改**：check_acceptance.py id 唯一性校验失败 -> 退出码 2 -> 触发下一轮，Leader 从 git 恢复（参考 biubiubiu SKILL 的备份步骤）

## 四、边界与已知限制

- 本脚本是 **Leader agent 的阅读材料**，不是可执行程序
- Leader 按消息驱动模型跑，不使用 time.sleep()
- `wait_all_dev_done()` / `wait_qa_done()` 是抽象调用，Leader 通过检查团队消息确定
- 若 Leader 读本脚本发现与自身能力矛盾（如无 subprocess 工具），优先按 biubiubiu SKILL 文字执行

## 五、退出码

本脚本若被直接运行（非预期），总是返回 0 + stdout 提示用户阅读 docstring。
"""
from __future__ import annotations

import sys


def fix_loop_runbook(feature: str) -> int:  # pragma: no cover
    """伪代码占位：此函数不会被真正调用。

    Leader agent 读完上方 docstring 后自行执行循环语义，不走此函数。
    """
    # pseudocode placeholders - 语法合法，实际执行另走 agent 循环
    round_cnt = 0
    last_failures: set[str] | None = None
    while round_cnt < 10:
        result_code = 0  # pseudo: subprocess check_acceptance.py
        if result_code == 0:
            break
        current_failures: set[str] = set()  # pseudo: parse JSON
        if last_failures is not None and last_failures == current_failures:
            # AskUserQuestion + break
            break
        # SendMessage to Dev / QA ...
        last_failures = current_failures
        round_cnt += 1
    return 0


def main() -> int:
    sys.stdout.write(
        "This is a runbook, read the docstring; do not execute directly.\n"
        "Leader agent 应按 docstring 中的循环语义自行驱动 SendMessage / 校验循环。\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
