#!/usr/bin/env python3
"""rpiv-loop 特性级验收判据（AC）校验脚本。

定位 rpiv/validation/<feature>/acceptance.yaml（或扁平兼容路径），
逐条校验 blocking AC 的 status/evidence 完整性，非 0 退出码拒绝 delivery-report。

退出码语义:
  0 = 所有 blocking AC 为 passed 或 not_applicable（且 evidence/notes 非空）
  1 = 至少一条 blocking AC 为 failed / 空 status / 缺字段 / evidence 不合规
  2 = acceptance.yaml 缺失 / YAML 解析错误 / id 冲突等结构性错误

YAML 解析策略: stdlib 正则（与 validate_rpiv_status.py 范式一致，零依赖）。
仅针对本项目 acceptance.yaml 的规整 schema；若未来 schema 复杂化，回退 PyYAML。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LEGAL_STATUS = {"passed", "failed", "not_applicable"}

# 匹配每条 AC item 的起始（行首 "- id:" 或缩进 "  - id:"）
ITEM_START_RE = re.compile(r"^(\s*)- id:\s*(.*)$", re.MULTILINE)

# 单个字段提取（匹配 "key: value"，value 支持带引号或裸字符串，单行）
FIELD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _field_re(key: str) -> re.Pattern[str]:
    """构造提取某字段的正则（缓存）。"""
    if key not in FIELD_RE_CACHE:
        FIELD_RE_CACHE[key] = re.compile(
            rf"^\s*{re.escape(key)}:\s*(.*?)\s*$", re.MULTILINE
        )
    return FIELD_RE_CACHE[key]


def _strip_value(raw: str) -> str:
    """去除 YAML scalar 两端引号与空白。"""
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v


def _parse_bool(raw: str) -> bool | None:
    v = _strip_value(raw).lower()
    if v in ("true", "yes", "on"):
        return True
    if v in ("false", "no", "off"):
        return False
    return None


def locate_acceptance(feature: str, cwd: Path | None = None) -> Path | None:
    """定位 acceptance.yaml：子目录优先，扁平兼容 fallback。"""
    base = (cwd or Path.cwd()) / "rpiv" / "validation"
    candidates = [
        base / feature / "acceptance.yaml",
        base / f"acceptance-{feature}.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def split_items(text: str) -> list[str]:
    """按 "- id:" 起始切分出每条 AC 的文本块。"""
    matches = list(ITEM_START_RE.finditer(text))
    if not matches:
        return []
    blocks: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(text[start:end])
    return blocks


def parse_item(block: str) -> dict[str, str]:
    """从一个 AC block 中抽取所需字段。"""
    fields: dict[str, str] = {}
    # id 字段特殊处理：block 首行形如 "  - id: AC-001"，不匹配标准 "  id:" 缩进
    id_match = ITEM_START_RE.search(block)
    fields["id"] = _strip_value(id_match.group(2)) if id_match else ""
    for key in ("status", "evidence", "blocking", "notes", "verification_method"):
        m = _field_re(key).search(block)
        fields[key] = _strip_value(m.group(1)) if m else ""
    return fields


def evaluate(items: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """返回 (failures, passed, structural_errors)。

    - failures: 每条失败的 AC 理由（退出码 1）
    - passed: 通过的 AC 条目（用于摘要统计）
    - structural_errors: 结构性错误，例如 id 重复、id 为空（退出码 2）
    """
    failures: list[str] = []
    passed: list[dict[str, str]] = []
    structural_errors: list[str] = []

    seen_ids: set[str] = set()
    for idx, item in enumerate(items, start=1):
        ac_id = item.get("id", "").strip()
        if not ac_id:
            structural_errors.append(f"item#{idx}: id 为空")
            continue
        if ac_id in seen_ids:
            structural_errors.append(f"{ac_id}: id 重复")
            continue
        seen_ids.add(ac_id)

        vm = item.get("verification_method", "").strip()
        if not vm:
            failures.append(f"{ac_id}: verification_method 为空")
            continue

        blocking_raw = item.get("blocking", "")
        blocking = _parse_bool(blocking_raw)
        # blocking 字段缺失时默认 true（PRD 4.2 场景 6 边缘情况）
        if blocking is None:
            blocking = True

        status = item.get("status", "").strip()
        evidence = item.get("evidence", "").strip()
        notes = item.get("notes", "").strip()

        if blocking:
            if status not in {"passed", "not_applicable"}:
                failures.append(
                    f"{ac_id}: status={status or '<empty>'} (expected passed/not_applicable)"
                )
                continue
            if status == "passed" and not evidence:
                failures.append(f"{ac_id}: evidence empty but status=passed")
                continue
            if status == "not_applicable" and not notes:
                failures.append(
                    f"{ac_id}: status=not_applicable but notes empty (需说明理由)"
                )
                continue
        else:
            if not status:
                failures.append(f"{ac_id}: non-blocking but status empty")
                continue
            if status not in LEGAL_STATUS:
                failures.append(
                    f"{ac_id}: status={status!r} 非法 (合法值: passed/failed/not_applicable)"
                )
                continue

        passed.append(item)

    return failures, passed, structural_errors


def build_json(
    feature: str,
    exit_code: int,
    failures: list[str],
    passed: list[dict[str, str]],
    structural_errors: list[str],
) -> str:
    payload = {
        "exit_code": exit_code,
        "feature": feature,
        "failures": [
            {"id": f.split(":", 1)[0].strip(), "reason": f.split(":", 1)[1].strip()}
            for f in failures
            if ":" in f
        ],
        "passed": [p["id"] for p in passed],
        "structural_errors": structural_errors,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="rpiv-loop AC 校验")
    parser.add_argument("feature", help="特性名（kebab-case）")
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="严格模式（默认启用）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式（给 hook 用）",
    )
    args = parser.parse_args()

    feature = args.feature.strip()
    if not feature:
        sys.stderr.write("[rpiv-loop] 缺少 feature 参数\n")
        return 2

    target = locate_acceptance(feature)
    if target is None:
        msg = (
            f"[rpiv-loop] acceptance.yaml 未找到\n"
            f"  已查找:\n"
            f"    rpiv/validation/{feature}/acceptance.yaml\n"
            f"    rpiv/validation/acceptance-{feature}.yaml\n"
            f"  请在 plan-feature 阶段产出 acceptance.yaml。\n"
        )
        if args.json:
            sys.stdout.write(
                build_json(feature, 2, [], [], ["acceptance.yaml not found"])
            )
            sys.stdout.write("\n")
        else:
            sys.stderr.write(msg)
        return 2

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"[rpiv-loop] 读取失败 {target.as_posix()}: {exc}\n")
        return 2

    blocks = split_items(text)
    if not blocks:
        msg = (
            f"[rpiv-loop] acceptance.yaml 未发现 AC 条目\n"
            f"  文件: {target.as_posix()}\n"
            "  期望 criteria 数组含至少 1 条 '- id: AC-NNN' 格式条目。\n"
        )
        if args.json:
            sys.stdout.write(build_json(feature, 2, [], [], ["no AC items found"]))
            sys.stdout.write("\n")
        else:
            sys.stderr.write(msg)
        return 2

    items = [parse_item(b) for b in blocks]
    failures, passed, structural_errors = evaluate(items)

    if structural_errors:
        exit_code = 2
        if args.json:
            sys.stdout.write(
                build_json(feature, exit_code, failures, passed, structural_errors)
            )
            sys.stdout.write("\n")
        else:
            sys.stderr.write("[rpiv-loop] acceptance.yaml 结构性错误:\n")
            for err in structural_errors:
                sys.stderr.write(f"  {err}\n")
        return exit_code

    if failures:
        exit_code = 1
        if args.json:
            sys.stdout.write(
                build_json(feature, exit_code, failures, passed, structural_errors)
            )
            sys.stdout.write("\n")
        else:
            sys.stdout.write(
                f"[FAILED] {len(failures)}/{len(items)} blocking AC not passed:\n"
            )
            for f in failures:
                sys.stdout.write(f"  {f}\n")
        return exit_code

    # 全部通过
    blocking_cnt = sum(1 for it in items if _parse_bool(it.get("blocking", "")) is not False)
    not_applicable = [p["id"] for p in passed if p.get("status") == "not_applicable"]
    if args.json:
        sys.stdout.write(build_json(feature, 0, [], passed, []))
        sys.stdout.write("\n")
    else:
        suffix = ""
        if not_applicable:
            suffix = f", {len(not_applicable)} not_applicable ({', '.join(not_applicable)})"
        sys.stdout.write(
            f"[OK] {len(passed)}/{len(items)} AC passed (blocking: {blocking_cnt}){suffix}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
