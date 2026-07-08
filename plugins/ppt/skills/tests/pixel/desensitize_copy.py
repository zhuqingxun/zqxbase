# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""华为主题 reference 资产脱敏拷贝脚本（Plan T1 A+B 混合方案）。

功能：
- 从 C:/Users/zqx/AppData/Local/Temp/hw-ppt-analysis/ 拷贝 reference 资产到
  D:/CODE/plugins/ppt/themes/huawei/reference/
- **B 方案（排除）**：不拷贝 `Consulting Deck Template.html` 和 `index.html`（含敏感词过多）
- **A 方案（替换）**：对 templates/*.html + assets/*.css 内残留敏感词逐条替换占位符
- **禁止**复制 `uploads/` 目录（PRD §7.5 规定）

用法：
    uv run --script tests/pixel/desensitize_copy.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

SRC = Path("C:/Users/zqx/AppData/Local/Temp/hw-ppt-analysis")
DST = Path("D:/CODE/plugins/ppt/themes/huawei/reference")


# 脱敏替换规则（按 Plan §T1 + Leader 决策）。替换顺序敏感：长 key 必须先于短 key。
# 规则覆盖 PRD §7.5.1 的 22 条关键字（在 templates/ 和 assets/ 内已知可能残留的）。
REPLACEMENTS: list[tuple[str, str]] = [
    # 角色（长词优先）
    ("CEO · 决策者", "{决策者}"),
    ("CIO · 架构负责人", "{架构负责人}"),
    ("CTO · 技术负责人", "{技术负责人}"),
    ("CEO·决策者", "{决策者}"),
    ("CIO·架构负责人", "{架构负责人}"),
    ("CTO·技术负责人", "{技术负责人}"),
    # 客户/行业
    ("商业银行", "{行业}"),
    ("金融机构", "{行业}"),
    ("银行", "{行业}"),
    # 项目代号
    ("大模型", "{AI能力}"),
    ("高层主打", "{核心胶片}"),
    # 语境词
    ("咨询胶片", "参考胶片"),
    ("真实项目", "示例项目"),
    ("客户案例", "示例案例"),
    # 内部术语
    ("保密", "内部"),
    ("机密", "内部"),
    # 职位/人名泛指
    ("项目经理", "项目负责人"),
    ("客户总监", "业务总监"),
    ("客户经理", "业务经理"),
    # 地名
    ("北京", "{总部城市}"),
    ("上海", "{总部城市}"),
    ("深圳", "{总部城市}"),
    ("广州", "{总部城市}"),
    # 合规标签
    ("仅限内部", "示例用途"),
    ("仅供参考", "示例用途"),
    ("内部使用", "示例用途"),
    ("商密", "示例"),
]

# 正则替换（对更复杂的模式）：
REGEX_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    # 版本号 25.0.x
    (re.compile(r"\b25\.0(?:\.\d+)?\b"), "{版本号}"),
    # CEO/CIO/CTO 单独出现（去除残留）
    (re.compile(r"\bCEO\b"), "{决策者}"),
    (re.compile(r"\bCIO\b"), "{架构负责人}"),
    (re.compile(r"\bCTO\b"), "{技术负责人}"),
    # NDA
    (re.compile(r"\bNDA\b"), "{合规约束}"),
    # AI 平台（与"AI能力"占位符合并）
    (re.compile(r"AI\s?平台"), "{AI能力}"),
    # 个人邮箱域名
    (re.compile(r"@(?:qq|163|126)\.(?:com|cn)"), "@example.com"),
    # 内部 URL
    (
        re.compile(
            r"https?://[\w.-]+\.(?:cn|com)/[\w/-]*(?:project|customer|internal)",
            re.IGNORECASE,
        ),
        "https://example.com/path",
    ),
    # 姓名带称谓（张总/李女士等）
    (re.compile(r"[一-龥]{2,4}(?:先生|女士|总)"), "{角色}"),
    # XX 公司/集团/银行 残留
    (re.compile(r"[Xx]{2,}(?:公司|集团|银行)"), "{公司占位}"),
]


def desensitize_text(text: str) -> str:
    """对单个文本应用所有脱敏规则。"""
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    for pattern, repl in REGEX_REPLACEMENTS:
        text = pattern.sub(repl, text)
    return text


def copy_text_with_desensitize(src_path: Path, dst_path: Path) -> int:
    """拷贝文本文件并做脱敏替换，返回替换前后差异行数估计。"""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_text = src_path.read_text(encoding="utf-8")
    dst_text = desensitize_text(src_text)
    dst_path.write_text(dst_text, encoding="utf-8")
    return 0 if src_text == dst_text else 1


def copy_binary(src_path: Path, dst_path: Path) -> None:
    """原样拷贝二进制（如截图）。"""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)


def copy_dir_binary(src_dir: Path, dst_dir: Path) -> int:
    """递归原样拷贝二进制目录。返回文件数。"""
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    return sum(1 for _ in dst_dir.rglob("*") if _.is_file())


def main() -> None:
    """执行脱敏拷贝（B 排除 + A 替换）。"""
    print(f"[T1] 源目录: {SRC}")
    print(f"[T1] 目标目录: {DST}")

    if not SRC.is_dir():
        raise FileNotFoundError(f"源目录不存在: {SRC}")

    # B 方案：需要排除的文件
    excluded = {"Consulting Deck Template.html", "index.html"}

    DST.mkdir(parents=True, exist_ok=True)

    # 1. assets/*.css + *.js（需脱敏）
    assets_src = SRC / "assets"
    assets_dst = DST / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)
    text_exts = {".css", ".js"}
    for f in assets_src.iterdir():
        if f.is_file() and f.suffix in text_exts:
            changed = copy_text_with_desensitize(f, assets_dst / f.name)
            print(f"  [assets] {f.name}{'  (已替换)' if changed else ''}")

    # 2. 顶层文本文件（deck-stage.js / styles.css）——需脱敏
    for name in ("deck-stage.js", "styles.css"):
        src_file = SRC / name
        if src_file.is_file():
            changed = copy_text_with_desensitize(src_file, DST / name)
            print(f"  [root] {name}{'  (已替换)' if changed else ''}")

    # 3. templates/*.html（需脱敏，按 B 方案 index.html 不在此目录，不排除）
    tpl_src = SRC / "templates"
    tpl_dst = DST / "templates"
    tpl_dst.mkdir(parents=True, exist_ok=True)
    count_tpl = 0
    for f in sorted(tpl_src.iterdir()):
        if f.is_file() and f.suffix == ".html":
            changed = copy_text_with_desensitize(f, tpl_dst / f.name)
            count_tpl += 1
            print(f"  [templates] {f.name}{'  (已替换)' if changed else ''}")
    print(f"  [templates] 共 {count_tpl} 个 HTML 文件")

    # 4. screenshots/ 整目录原样拷贝（截图非文本，不扫描）
    ss_src = SRC / "screenshots"
    ss_dst = DST / "screenshots"
    if ss_src.is_dir():
        n = copy_dir_binary(ss_src, ss_dst)
        print(f"  [screenshots] {n} 个文件")
    else:
        print("  [screenshots] 源目录不存在，跳过")

    # 5. 确认 B 方案排除生效
    for name in excluded:
        skipped = SRC / name
        if skipped.is_file():
            print(f"  [SKIP 按 B 方案排除] {name}")

    # 6. 确认 uploads/ 未复制
    uploads_dst = DST / "uploads"
    assert not uploads_dst.exists(), f"uploads/ 不应存在于目标: {uploads_dst}"

    print("[T1] 完成")


if __name__ == "__main__":
    main()
