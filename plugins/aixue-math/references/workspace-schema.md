# workspace.yaml Schema（课时工作区元数据）

本文件定义 aixue-math 工作区 `.aixue/workspace.yaml` 的完整 schema。所有 `aixue-math:*` skill 读写 workspace.yaml 必须遵循本规范。

实际读写入口：`scripts/workspace_io.py`（封装 YAML I/O、状态更新、字段顺序保障），SKILL.md 不直接 load/dump yaml。

## 课题目录命名（强制）

`workspaces/` 与 `_dist/` 下的课题目录统一带两位序号前缀 `NN_<课题名>`（例 `01_周长_什么是周长`），两侧一一镜像。序号仅供文件管理器排序索引，由 `workspace_io.py next-seq` 单调追加分配（取当前最大 +1，**不重排既有编号**）。

`workspace.name` 存**去掉前缀**的纯课题名 —— 序号是文件系统层的排序辅助，不是课题标识的一部分；教案 frontmatter 的 `lesson_workspace` 同样取不带序号的 `name`。需要从目录名反推时用 `workspace_io.strip_seq_prefix()`。

## 字段顺序规范（强制）

`save_workspace` 写入时必须保持以下顺序：

```
workspace / inputs / outputs / revisions / current / next_hints
```

## 完整 Schema

```yaml
workspace:                            # 基础信息，必填
  name: string                        # 课时名（= 目录名去掉 NN_ 序号前缀，例：周长_什么是周长）
  title: string                       # 实际课题（例：什么是周长）
  grade: string                       # 年级（例：三年级下册）
  subject: string                     # 学科（默认：数学）
  textbook_edition: string            # 教材版本（例：北师大版）
  unit: string                        # 所属单元（例：第三单元 周长）
  lesson_type: string                 # 课型（新授课/练习课/复习课/综合实践课）
  duration_minutes: int               # 课时时长（默认 40）
  created: date                       # 创建日期（YYYY-MM-DD）
  shared_dir: string                  # 全局共享资源根路径（绝对或相对 workspace 的）
  dist_dir: string                    # 成品输出根，默认 ../../_dist/<工作区目录名>（含 NN_ 序号前缀）

inputs:                               # 4 类输入状态
  textbook:                           # 输入 (1) 教材
    status: enum[pending|extracted|verified]   # 必填
    source_pdf: string | null         # 原 PDF 绝对路径
    pdf_pages: string | null          # PDF 物理页范围，如 "36-38"
    book_pages: string | null         # 书本印刷页范围，如 "33-35"
    extracted_at: ISO8601 | null      # 提取完成时间
    extracted_md: string | null       # extracted/ 下产物 MD 相对路径
  knowledge:                          # 输入 (2) 知识点
    status: enum[pending|extracted|verified]
    source: string | null             # 参考书 / URL / 描述
    extracted_md: string | null
  guidelines:                         # 输入 (3) 写作要求（默认引用 shared/）
    status: enum[ref_only|customized]
    ref_path: string                  # 默认 shared_dir/03_写作要求/
  samples:                            # 输入 (4) 教案样例（默认引用 shared/）
    status: enum[ref_only|customized]
    ref_path: string                  # 默认 shared_dir/04_教案样例/

outputs:
  lesson_plan:                        # 【已废弃，仅保留兼容性】单课时产出槽位
    status: enum[pending|draft|final]
    draft_md: string | null
    final_md: string | null
    version: int
    generated_at: ISO8601 | null
  lessons:                            # 多课时产出映射，键为课时号字符串 "1"/"2"/...
    "<lesson_num>":                   # 一个 workspace 可对应 1-N 个课时（常见 1-3）
      title: string                   # 课时标题（如 "什么是周长·认识与测量"）
      current_version: int            # 当前版本号（根目录里那版的 v<N>；每次 refine 递增）
      md: string | null               # 05_教案/md/v<N>-课时<K>-<title>.md（最新版）
      docx: string | null             # 05_教案/docx/*.docx（md 的同步 Word 副本）
      html: string | null             # 05_教案/html/*.html（图文并茂自包含 HTML）
      pdf: string | null              # 05_教案/pdf/*.pdf（HTML 印刷版 PDF）
      board_ref: string | null        # 反向关联板书，如 outputs.boards.'1'
      board_embedded: string | null   # 板书是否已嵌入教案正文（'true'/'false'）
      generated_at: ISO8601 | null
      # 无 status / draft_* / final_* / previous_md：当前版 = 根目录里那版，
      # 历史版本自动降级到 05_教案/OLD/<fmt>/（由 workspace_io rotate-versions 维护）
  boards:                             # 多课时板书产出映射，与 lessons【平级】（不是 lessons 的子级）
    "<lesson_num>":                   # 键为课时号字符串，与 lessons.<N> 通过 ref 互引
      title: string                   # 板书标题（如 "什么是周长·认识与测量 — 板书设计"）
      lesson_ref: string              # 反向关联教案，如 outputs.lessons.'1'
      current_png_version: int        # 当前 PNG 渲染版本（06_板书/课时<N>/png/ 里 -v<V>；旧版在 课时<N>/OLD/）
      generated_at: ISO8601 | null
      style: string                   # 视觉风格（如 "黑板粉笔风"）
      layout: string                  # 四分区布局描述
      color_scheme: map               # 各分区色彩语义（red/blue/green/white/yellow/pink）
      formats:
        infographic:                  # 单张大图（贴黑板边 / 打印 A3 / 发家长）
          html: string                # 06_板书/课时<N>/infographic.html
          png: string                 # 06_板书/课时<N>/png/infographic-v<V>.png
        slide_deck:                   # 多页逐屏（课堂多媒体）
          html: string                # 06_板书/课时<N>/slide-deck.html
          pages: int
          png_pages: list[string]     # 06_板书/课时<N>/png/slide-<i>-v<V>.png
      render_script: string           # 06_板书/render.py（一份脚本服务所有课时）
      generation_method: string       # 渲染方式说明（本地 HTML+CSS+Playwright）

revisions: list                       # 修订历史（初始 []）
  - timestamp: ISO8601
    description: string
    affected_files: list[string]

current:                              # 当前游标
  cursor: string | null               # 最近活跃阶段（textbook / knowledge / generate / refine）
  last_action: ISO8601 | null
  last_action_desc: string | null
  blockers: list                      # 待用户决策项（初始 []）
    - type: enum[ambiguity|missing_input|user_decision]
      description: string
      suggested_action: string

next_hints:                           # 下一步引导（由各 skill 写入，status/next 消费）
  primary:
    cmd: string | null
    reason: string | null
  alternatives: list                  # 初始 []
    - cmd: string
      when: string
```

## 状态枚举语义

### inputs.textbook.status / inputs.knowledge.status

- `pending`：尚未处理（默认初始值）
- `extracted`：已经产出 extracted_md，但用户未核对
- `verified`：用户核对通过、确认准确（可进入 generate）

### inputs.guidelines.status / inputs.samples.status

- `ref_only`：引用全局 `shared_dir` 下资源（默认值，**推荐**）
- `customized`：workspace 内有本地同名目录覆盖（用户明确需要课时特定内容时）

### outputs.lessons.<N> / outputs.boards.<N> 的版本模型（无 status 枚举）

不再用 `draft/reviewed/final` 状态机。约定「**当前版 = 根目录里那版**」：

- 教案：`05_教案/{md,docx,html,pdf}/` 各只放每课时最新一版，`current_version` 记其 `v<N>`；
  生成新版后由 `workspace_io rotate-versions` 把旧版本降级到 `05_教案/OLD/<fmt>/`。
- 板书：`06_板书/课时<N>/png/` 放当前渲染版，`current_png_version` 记其 `v<V>`；
  旧版 PNG 由 `render.py` 渲染新版时移入 `06_板书/课时<N>/OLD/`。
- 想把某历史版重新当作当前版：把该版文件从 `OLD/` 移回根（或重渲染），并改 `current_version`。

### outputs.lesson_plan.status（已废弃）

`lesson_plan` 是迁移前的单课时槽位，仅保留兼容，真实状态看 `lessons.<N>`。不再有 `05_教案/draft`、`05_教案/final` 目录。

## 字段约束

- `workspace.name` 与目录名一致，skill 读写时以 name 为准（目录重命名需同步更新此字段）
- `workspace.shared_dir` 存相对路径时基于 workspace 根目录解析；存绝对路径则直接用
- `inputs.*.status` 推进遵循单调性：pending → extracted → verified（不可倒退除非有 revision）
- `revisions` 每次 skill 修改文件后追加一条
- `current.cursor` 仅由流水线 skill（textbook / knowledge / generate / refine）更新；status/next 等只读

## 缺字段报错行为

`load_workspace` 执行时必须校验 `workspace`、`inputs`、`outputs`、`current`、`next_hints` 五块存在。缺任一抛 `KeyError("workspace.yaml 缺少必要字段 <field>")`。

v0.x 不做向后兼容；schema 演进通过一次性升级脚本处理。
