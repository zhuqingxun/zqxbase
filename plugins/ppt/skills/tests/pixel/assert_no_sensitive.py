# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""华为主题脱敏扫描断言模块（PRD §7.5.1 K01-K22 + §7.5.2 白名单）。

两种 API：

1. `scan(root: Path) -> int`  —— 返回命中数，供 QA 测试 `tests/security/test_desensitization.py` 调用。
2. `assert_no_sensitive(root: Path, whitelist: list[dict] | None = None) -> list[dict]`
   返回命中列表，供门禁 / 发布流水线调用。

可作脚本直接运行：`python tests/pixel/assert_no_sensitive.py <root>`，exit code = 命中数。

白名单规则（PRD §7.5.2）：

- `README.md` 中整行包含 "参考华为胶片风格" 的行被放行
- `assets/theme.css` 中注释 "/* 参考原PPT红灰色系..." 行被放行
- `tokens.yaml` / `layouts.yaml` 文件内的所有命中被放行（颜色名注释本身是设计来源说明）
- `reference/templates/*.html` 中已占位化的 `{...}`（全中文 / 数字）本身不是 K# 命中

白名单**不绕过**真实 K# 命中：如 README 中出现 K08 "咨询胶片" 仍必须 FAIL。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple


# ==================== PRD §7.5.1 22 条关键字规则 ====================


class Rule(NamedTuple):
    kid: str
    category: str
    pattern: re.Pattern
    description: str


def _literal(s: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    """生成字面量 pattern（大小写不敏感）。"""
    return re.compile(re.escape(s), flags)


# 注意顺序：长词 / 更严格的正则在前，避免被短词误盖
RULES: list[Rule] = [
    # 客户 / 行业
    Rule("K02", "客户/行业", _literal("商业银行"), "具体行业主体"),
    Rule("K01", "客户/行业", _literal("银行"), "源 PDF 标题泄露词"),
    Rule("K03", "客户/行业", _literal("金融机构"), "通用客户代称"),
    # 项目代号
    Rule("K04", "项目代号", _literal("大模型"), "源 PDF 标题核心词"),
    Rule("K05", "项目代号", re.compile(r"AI\s?平台", re.IGNORECASE), "内部代号变体"),
    Rule("K06", "项目代号", _literal("高层主打"), "源 PDF 标题词"),
    # 版本号
    Rule("K07", "版本号", re.compile(r"25\.0(?:\.[0-9]+)?"), "源 PDF 版本号"),
    # 语境词
    Rule("K08", "语境词", _literal("咨询胶片"), "项目定位泄露完整短语"),
    Rule("K09", "语境词", _literal("真实项目"), "开发残留标记"),
    Rule("K10", "语境词", _literal("客户案例"), "开发残留标记"),
    # 内部术语
    Rule("K11", "内部术语", _literal("保密"), "合规敏感词"),
    Rule("K12", "内部术语", _literal("机密"), "合规敏感词"),
    Rule("K13", "内部术语", re.compile(r"\bNDA\b", re.IGNORECASE), "保密协议缩写"),
    # 人名 / 职位
    Rule("K14", "人名/职位", _literal("项目经理"), "咨询文件常见角色"),
    Rule("K15", "人名/职位", re.compile(r"客户(?:总监|经理)", re.IGNORECASE), "客户方角色"),
    Rule("K16", "人名/职位", re.compile(r"\b(?:CIO|CTO|CEO)\b", re.IGNORECASE), "职位代称"),
    # K17: 中文姓名带称谓。规则：
    # - "X先生/X女士" 无歧义，直接匹配；
    # - "X总" 仅当"总"后不是明确的岗位/机构后缀（监/部/裁/经理/工程师）时命中，
    #   以排除"市场总监 / 公司总部 / 总经理"等岗位/机构名。
    Rule(
        "K17",
        "人名/职位",
        re.compile(
            r"[一-龥]{1,3}(?:先生|女士)"
            r"|[一-龥]{1,3}总(?!(?:监|部|裁|理|经理|工程师))"
        ),
        "中文姓名带称谓",
    ),
    # 占位残留
    Rule("K18", "占位残留", re.compile(r"[Xx]{2,}(?:公司|集团|银行)"), "XX 占位未替换"),
    # 地名
    Rule("K19", "地名", re.compile(r"(?:北京|上海|深圳|广州)"), "客户地址线索"),
    # 个人邮箱
    Rule("K20", "个人邮箱", re.compile(r"@(?:qq|163|126)\.(?:com|cn)", re.IGNORECASE), "个人邮箱域名"),
    # 内部 URL
    Rule(
        "K21",
        "内部 URL",
        re.compile(
            r"https?://[\w.-]+\.(?:cn|com)/[\w/-]*(?:project|customer|internal)",
            re.IGNORECASE,
        ),
        "含 project/customer/internal 的内部链接",
    ),
    # 合规标签
    Rule(
        "K22",
        "合规敏感",
        re.compile(r"(?:商密|内部使用|仅供参考|仅限内部)", re.IGNORECASE),
        "合规标签",
    ),
]


# 扫描对象的文本扩展名（PRD §7.5 明示）
TEXT_EXTENSIONS: set[str] = {
    ".html", ".css", ".js", ".md", ".yaml", ".yml", ".txt",
}


# ==================== 默认白名单（PRD §7.5.2） ====================


# 单条白名单条目结构：
#   path_suffix:   文件路径后缀匹配（相对 root），如 "README.md" / "assets/theme.css"
#   line_contains: 命中行必须包含的子串；满足则放行
#   skip_whole:    true 表示该路径下所有命中都放行（如 tokens.yaml 色值注释）
DEFAULT_WHITELIST: list[dict] = [
    # WL-1: README.md 中 "参考华为胶片风格" 整行放行
    {"path_suffix": "README.md", "line_contains": "参考华为胶片风格"},
    # WL-2: assets/theme.css 中注释行放行
    {"path_suffix": "assets/theme.css", "line_contains": "参考原PPT红灰色系"},
    # WL-3: tokens.yaml / layouts.yaml 色名注释放行
    {"path_suffix": "tokens.yaml", "skip_whole": True},
    {"path_suffix": "layouts.yaml", "skip_whole": True},
]


# ==================== 扫描实现 ====================


class Hit(NamedTuple):
    kid: str
    category: str
    file: Path
    line_no: int
    line_text: str
    matched: str

    def to_dict(self) -> dict:
        return {
            "kid": self.kid,
            "category": self.category,
            "file": str(self.file),
            "line": self.line_no,
            "line_text": self.line_text.rstrip("\n"),
            "matched": self.matched,
        }


def _is_whitelisted(
    rel_path: str,
    line_text: str,
    whitelist: list[dict],
) -> bool:
    """判断一条命中是否被白名单放行。"""
    rel_norm = rel_path.replace("\\", "/")
    for entry in whitelist:
        suffix = entry.get("path_suffix", "")
        if suffix and not rel_norm.endswith(suffix):
            continue
        if entry.get("skip_whole"):
            return True
        lc = entry.get("line_contains")
        if lc and lc in line_text:
            return True
    return False


def _iter_text_files(root: Path):
    """遍历 root 下所有受扫描的文本文件，跳过 uploads 目录。"""
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # 跳过 uploads/（PRD §7.5 明示不入发布包，但源目录下可能残留）
        if any(part.lower() == "uploads" for part in p.parts):
            continue
        if p.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        yield p


def assert_no_sensitive(
    root: Path,
    whitelist: list[dict] | None = None,
) -> list[dict]:
    """扫描 root 下文本文件，返回命中列表（经白名单过滤后）。

    Args:
        root: 扫描根目录
        whitelist: 白名单规则列表；None 使用 DEFAULT_WHITELIST

    Returns:
        list[dict]: 每条元素含 kid / category / file / line / line_text / matched
    """
    if whitelist is None:
        whitelist = DEFAULT_WHITELIST

    root = Path(root)
    if not root.is_dir():
        return []

    hits: list[Hit] = []
    for f in _iter_text_files(root):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(root))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule in RULES:
                m = rule.pattern.search(line)
                if m is None:
                    continue
                if _is_whitelisted(rel, line, whitelist):
                    continue
                hits.append(
                    Hit(
                        kid=rule.kid,
                        category=rule.category,
                        file=f,
                        line_no=line_no,
                        line_text=line,
                        matched=m.group(0),
                    )
                )
    return [h.to_dict() for h in hits]


def scan(root: Path, whitelist: list[dict] | None = None) -> int:
    """QA 测试入口：返回命中数（int）。

    用于 tests/security/test_desensitization.py 的 `scanner_module.scan(...)` 调用。
    """
    return len(assert_no_sensitive(root, whitelist))


# ==================== CLI ====================


def _format_report(hits: list[dict]) -> str:
    if not hits:
        return "PASS: 0 条敏感词命中"
    lines = [f"FAIL: {len(hits)} 条敏感词命中"]
    for h in hits:
        lines.append(
            f"  [{h['kid']}] {h['category']} | {h['file']}:{h['line']} "
            f"| matched={h['matched']!r}"
        )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: assert_no_sensitive.py <root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    hits = assert_no_sensitive(root)
    print(_format_report(hits))
    return len(hits)


if __name__ == "__main__":
    sys.exit(main())
