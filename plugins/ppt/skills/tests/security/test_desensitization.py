# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=7.0"]
# ///
"""T14 配套测试：22 条脱敏关键字扫描器的正/负例 red/green 测试。

被测对象：`tests/pixel/assert_no_sensitive.py`（Plan T14 交付的扫描脚本）。

覆盖范围：
- test_keyword_<K#>_red[<kid>]：red 样本命中时必须 FAIL
- test_keyword_<K#>_green[<kid>]：green 样本（同类别但非敏感）必须 PASS
- test_whitelist_<rule>：白名单规则能放行合法命中
- test_uploads_directory_absence：发布包不得包含 reference/uploads/
- test_sourcedir_scan_passes：源目录 themes/huawei/ 的整体扫描（需 Dev 先完成 T2/T3）

对应规格：SPEC-DS-* 全集。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# 延迟导入扫描脚本（T14 可能尚未交付；测试前先检查脚本存在）
_SCANNER_PATH = PLUGIN_ROOT / "tests" / "pixel" / "assert_no_sensitive.py"


def _load_scanner():
    """动态加载 tests/pixel/assert_no_sensitive.py 模块。"""
    if not _SCANNER_PATH.exists():
        pytest.skip(f"scanner not yet created by Dev (T14): {_SCANNER_PATH}")
    # 确保 tests/pixel 在 sys.path 上，以便作为模块导入
    pixel_pkg_path = str(_SCANNER_PATH.parent)
    if pixel_pkg_path not in sys.path:
        sys.path.insert(0, pixel_pkg_path)
    spec = importlib.util.spec_from_file_location("assert_no_sensitive", _SCANNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# PRD §7.5.1 的 22 条 K# 与 red sample、green sample 映射
# red: 必须被该 K# 命中的一句话
# green: 同类别但不该命中的一句话（用于防误报）
KEYWORD_CASES: list[tuple[str, str, str]] = [
    # (kid, red_sample, green_sample)
    ("K01", "这是某商业银行的案例分析",           "这是零售业的案例分析"),
    ("K02", "商业银行数字化转型方案",             "企业数字化转型方案"),
    ("K03", "金融机构客户洞察",                   "消费品行业客户洞察"),
    ("K04", "本项目基于大模型实现",               "本项目基于经典算法实现"),
    ("K05", "我们建设了 AI 平台",                 "我们建设了数据系统"),
    ("K06", "高层主打胶片",                       "团队晨会胶片"),
    ("K07", "版本号 25.0.0",                      "版本号 v1.2.3"),
    ("K08", "咨询胶片定稿",                       "示例幻灯片定稿"),
    ("K09", "这是一个真实项目",                   "这是一个示例项目"),
    ("K10", "客户案例分享",                       "教学案例分享"),
    ("K11", "保密协议已签",                       "协议已签"),
    ("K12", "机密资料",                           "公开资料"),
    ("K13", "See NDA for details",                "See README for details"),
    ("K14", "项目经理汇报进度",                   "产品负责人汇报进度"),
    ("K15", "客户总监出席会议",                   "市场总监出席会议"),
    ("K16", "The CIO approved the plan",          "The lead approved the plan"),
    ("K17", "张总参加了审议",                     "团队成员参加了审议"),
    ("K18", "XX公司合作",                         "示例合作"),
    ("K19", "北京总部的汇报",                     "公司总部的汇报"),
    ("K20", "联系 abc@qq.com",                    "联系 hello@example.org"),
    ("K21", "访问 https://internal.corp.cn/project/foo", "访问 https://docs.example.com/guide"),
    ("K22", "标注：仅限内部",                     "标注：公开发布"),
]


@pytest.fixture(scope="module")
def scanner_module():
    return _load_scanner()


@pytest.mark.parametrize("kid,red,green", KEYWORD_CASES, ids=[c[0] for c in KEYWORD_CASES])
def test_keyword_red_sample_is_flagged(scanner_module, tmp_path, kid, red, green):
    """red 样本：至少被对应 K# 命中一次。"""
    # 构造一个临时文件放入 red 文本
    (tmp_path / "sample.md").write_text(red, encoding="utf-8")
    fails = scanner_module.scan(tmp_path)
    assert fails >= 1, f"{kid} 的 red sample 未被任何 K# 规则命中: {red!r}"


@pytest.mark.parametrize("kid,red,green", KEYWORD_CASES, ids=[c[0] for c in KEYWORD_CASES])
def test_keyword_green_sample_passes(scanner_module, tmp_path, kid, red, green):
    """green 样本：与该 K# 类别相关但不应命中任何 K# 规则。"""
    (tmp_path / "sample.md").write_text(green, encoding="utf-8")
    fails = scanner_module.scan(tmp_path)
    assert fails == 0, f"{kid} 的 green sample 误触发 FAIL: {green!r}"


# ============================================================
# 白名单规则测试（PRD §7.5.2）
# ============================================================

def test_whitelist_readme_authorized_phrase(scanner_module, tmp_path):
    """README.md 中 "参考华为胶片风格" 整行应被放行，即使含 K08 '咨询胶片' 前缀也不豁免。

    PRD §7.5.2 WL-1 授权短语是"参考华为胶片风格"，不是"咨询胶片"。
    白名单短语本身不含 K# 关键字，所以 README 中只出现"参考华为胶片风格"应 0 命中。
    """
    readme_body = "# Huawei Theme\n\n参考华为胶片风格的 PPT 主题。\n"
    (tmp_path / "README.md").write_text(readme_body, encoding="utf-8")
    assert scanner_module.scan(tmp_path) == 0


def test_whitelist_readme_does_not_cover_k08(scanner_module, tmp_path):
    """SPEC-DS-12：README 中出现 K08 "咨询胶片" 必须 FAIL（不可通过 README 白名单放行）。"""
    bad_readme = "# Huawei Theme\n\n本主题来自咨询胶片原版。\n"
    (tmp_path / "README.md").write_text(bad_readme, encoding="utf-8")
    assert scanner_module.scan(tmp_path) >= 1


def test_whitelist_theme_css_comment(scanner_module, tmp_path):
    """theme.css 的 CSS 注释 "/* 参考原PPT红灰色系 */" 应被白名单放行。"""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    css_body = "/* 参考原PPT红灰色系，可通过 Tweaks 覆盖 */\n:root { --c-primary: #C7000B; }\n"
    (assets_dir / "theme.css").write_text(css_body, encoding="utf-8")
    assert scanner_module.scan(tmp_path) == 0


def test_whitelist_template_placeholder(scanner_module, tmp_path):
    """reference/templates/*.html 中 {公司占位} / {能力1} 等占位符应放行。"""
    tpl_dir = tmp_path / "reference" / "templates"
    tpl_dir.mkdir(parents=True)
    html_body = "<div>{公司占位} 在 {行业/主题} 领域的 {能力1} 应用</div>\n"
    (tpl_dir / "01-封面.html").write_text(html_body, encoding="utf-8")
    assert scanner_module.scan(tpl_dir.parent.parent) == 0


def test_whitelist_tokens_yaml_color_comment(scanner_module, tmp_path):
    """tokens.yaml 中 # 主红 这类色名注释应放行。"""
    body = 'colors:\n  primary: "#C7000B"  # 主红\n  ink_dark: "#2A2A2A"  # 章节页深底\n'
    (tmp_path / "tokens.yaml").write_text(body, encoding="utf-8")
    assert scanner_module.scan(tmp_path) == 0


# ============================================================
# 发布包结构断言（SPEC-DS-1/2/14/15/16）
# ============================================================

RELEASE_DIR = Path("D:/CODE/plugin_test/skills-release/ppt/themes/huawei")
SOURCE_DIR = Path("D:/CODE/plugins/ppt/themes/huawei")


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="发布包尚未生成（Dev T17 前）")
def test_uploads_directory_absent_from_release():
    """SPEC-DS-1：发布包不得存在 reference/uploads/ 目录或为空。"""
    uploads = RELEASE_DIR / "reference" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="发布包尚未生成（Dev T17 前）")
def test_no_pdf_in_release_tree():
    """SPEC-DS-2：发布包任一层级都不得含 .pdf 文件。"""
    pdfs = list(RELEASE_DIR.rglob("*.pdf"))
    assert not pdfs, f"发布包含 PDF 文件: {[str(p) for p in pdfs]}"


@pytest.mark.skipif(not SOURCE_DIR.exists(), reason="源目录尚未建立（Dev T2 前）")
def test_source_directory_scan_passes(scanner_module):
    """SPEC-DS-8：源目录 themes/huawei/ 全量扫描必须 0 命中（除白名单）。

    此测试在 Dev T2（目录骨架）+ T3（reference 复制）完成后才会生效。
    """
    fails = scanner_module.scan(SOURCE_DIR)
    assert fails == 0, f"源目录含 {fails} 条敏感词命中，参考 stdout 修源文件后重跑"


@pytest.mark.skipif(not RELEASE_DIR.exists(), reason="发布包尚未生成（Dev T17 前）")
def test_release_directory_scan_passes(scanner_module):
    """SPEC-DS-9：发布目录 skills-release/... 全量扫描必须 0 命中。"""
    fails = scanner_module.scan(RELEASE_DIR)
    assert fails == 0, f"发布包含 {fails} 条敏感词命中"
