# Interviewee Types & Templates 参考

本文件定义 `workspace.yaml` 中 `interviewee_types[]` 与 `templates[]` 两张注册表的 ID 约定、冲突处理、引用完整性规则，以及 polish 第零步的三层兜底决策树。

> **双份 source of truth**：本文档 + `scripts/meta_io.py`。若规则变更必须双向同步。代码以 `meta_io.py` 为 v1 判据。

## ID 约定

### 格式规范

- 正则：`^[a-z][a-z0-9-]*$`
- 推荐长度：3–30 字符
- 仅允许小写字母、数字、短横线
- 首字符必须为字母
- 不允许前导/尾部 `-`，不允许连续 `--`（建议实现，非强约束）

### 前缀约定（非强制）

- `interviewee_types[].id`：无前缀，直接使用概念名（如 `internal / external / leader`）
- `templates[].id`：建议 `tpl-` 前缀（如 `tpl-internal`），便于与 type id 区分

## 预设 name → id 映射表

`mint:init` 第 4 问 (interview 场景) 的 4 个预设选项 + 自动 Other 兜底，对应以下映射：

| 预设 name | 预设 id |
|-----------|---------|
| 内部员工 | `internal` |
| 外部员工 / 服务对象 | `external` |
| 领导层 | `leader` |

> 研究报告曾列出 4 个预设（额外含"专家顾问"），但 PRD 9.7 最终收敛到 3 预设 + Other。实现按 PRD 为准。

Other 兜底策略（`normalize_id()`）：
- 纯 ASCII 名：`name.lower()` + 非字母数字替换为 `-`
- 含非 ASCII（中文等）：`raise ValueError("name 含非 ASCII 字符，请改用英文名或手工指定 id")`
- 冲突：已存在同 id 时追加 `-2 / -3 / ...` 后缀

## ID 冲突处理

所有注册操作（types-add / templates-add / init 循环追加）共用 `normalize_id(name, existing_ids, prefix="")` helper：

```python
# 命中预设映射表 → 直接返回
normalize_id("内部员工", set()) == "internal"

# 纯 ASCII → kebab-case
normalize_id("tech staff", set()) == "tech-staff"

# 冲突 → 追加 -2
normalize_id("tech staff", {"tech-staff"}) == "tech-staff-2"

# 含非 ASCII → 报错
normalize_id("其他测试", set())  # ValueError
```

## 引用完整性规则

### types.remove 前置检查

删除一个 interviewee_type 之前：

1. 扫描所有会议 `meta.yaml` 的 `interviewee_type` 字段，若有引用 → 拒绝（exit 2 + `ERROR: type <id> 被以下会议引用: ...`）
2. 扫描 `workspace.templates[].applies_to`，若有引用 → 自动从 `applies_to` 列表中移除该 id（不拒绝，templates 保留）

### templates.remove 前置检查

删除一个 template 之前，`templates-remove` CLI 同时扫描两类引用（不短路），任一命中即拒绝并汇总列出：

1. 扫 `workspace.interviewee_types[].default_template_id`
2. 扫所有会议 `meta.stages.polish.params.template_override`
3. 若 types 或 meetings 任一非空 → `ERROR: template <id> 被以下引用: types=[...]; meetings=[...]` exit 2（CLI-06）
4. 通过后：从 workspace.yaml 删除条目 + 删除物理文件（若存在；不存在时宽容通过）

### templates.add 文件搬运 + 双向更新

`templates-add` CLI 的完整行为（skill 不需要自己做 mkdir/mv）：

1. 前置校验：`<file>`（绝对或相对工作区根）必须存在且为文件，否则 `ERROR: file not found: <path>` exit 2（NEG-TT-04）
2. 目标路径：`.mint/templates/<basename>`（保留原文件名，含中文全角字符）；若目标已存在且 src ≠ dest → `目标文件已存在，拒绝覆盖` exit 2
3. `shutil.move(src, dest)`；若 src 已等于 dest（原地文件）则免搬
4. `workspace.yaml.templates[].file` 存相对路径 `.mint/templates/<basename>`
5. `--set-default` 时遍历 `applies_to` 中每个 type id，将其 `default_template_id` 设为新 template id
6. workspace 写入失败时尝试回滚文件搬运，避免 yaml ↔ 文件状态不一致

> 重命名为 `<tpl-id>.<ext>` 的 sanitize 策略由独立 `upgrade_types_templates.py --sanitize` 提供，**不是** `templates-add` 的行为。

## Template 文件存储约定

### 推荐路径

`.mint/templates/<tpl-id>.<ext>`

通过 `workspace.yaml.templates[].file` 登记**相对工作区根**的路径（Windows 使用 forward-slash）。

### 中文文件名处理

- **默认保留原始文件名**（PRD 8.3 允许），中文和全角字符在 Windows NTFS + Python pathlib 下完全合法
- 迁移脚本 `upgrade_types_templates.py` 提供可选 `--sanitize` flag，会把文件重命名为 `<tpl-id>.<ext>` 避免外部工具对全角冒号的处理风险
- 新增路径约定：`.mint/templates/` 子目录由 `mint:templates add` 按需创建

### 中文冒号陷阱

`蓝军视角：某业务组织深度访谈提纲.pdf` 等含全角冒号的文件名：
- Python pathlib / shutil 完整支持
- NTFS 合法（全角 `：` != 半角 `:`）
- 但部分外部工具（bash grep、PDF 阅读器、Git 低版本）可能转义失败
- 作为 template 登记时建议 `--sanitize` 重命名为 ASCII 友好版

## Polish 第零步三层兜底决策树

```
输入：
  - CLI `--template` 值（可能 None）
  - meeting_dir/meta.yaml 的 interviewee_type 字段
  - workspace.yaml 的 interviewee_types[] / templates[]

分支 A: CLI --template 显式
  ├─ 值以 tpl- 开头或命中 templates[].id → 从注册表取
  │   → {template_path: "<root>/<file>", template_id: <id>, source: "explicit"}
  └─ 其他视为路径（绝对或相对工作区根）
      ├─ 文件存在 → {template_path: <绝对>, template_id: "adhoc", source: "explicit"}
      └─ 不存在 → ERROR: template <x> 不存在于注册表或路径 (exit 2)

分支 B: meta.interviewee_type 非空
  ├─ type id 不存在于 workspace → ERROR: 类型 <id> 不存在... (exit 2)
  └─ type 存在
      ├─ default_template_id 为空 → {template_path: None, source: "none"} (无模板模式)
      ├─ default_template_id 指向不存在 template → ERROR (exit 2)
      └─ 正常 → {template_path: "<root>/<file>", template_id: <id>, source: "type_default"}

分支 C: 兼容老工作区（meta 无 interviewee_type）
  ├─ workspace 有 types 注册 → ERROR: meta.yaml 缺少 interviewee_type，interview 场景必填，请手工编辑或跑升级脚本 (exit 2)
  └─ workspace 也无 types（老 schema） → {template_path: None, source: "none"} (无模板模式)
```

### 错误消息关键词（对应测试断言）

- NEG-TT-06: `template ... 不存在`
- NEG-TT-07: `类型 ... 不存在`
- NEG-TT-08: `default_template_id ... 指向不存在的 template`

### 无模板模式行为（template_path is None）

polish 的七维审查中"维度 1 观点覆盖度"需要模板才能评分。无模板模式下：
- 跳过维度 1
- Reviewer 权重从 25% 重分到维度 2-7（按比例）
- meta.yaml.stages.polish.review 字段标注 `mode: no_template`

详见 `polish/SKILL.md` 第零步与 Reviewer 章节。

## 与 meta.yaml 既有字段的关系

polish 改造前遗留字段（保留但新代码不再读取）：
- `meta.stages.polish.params.template`
- `meta.stages.polish.params.has_template`
- `meta.stages.polish.params.template_override`（保留：polish --template 显式覆盖时写入）

新 polish 代码一律走 `resolve-template` CLI 子命令，不再直接读取 `params.template` / `has_template`。历史会议的遗留字段不清理（不破坏兼容）。
