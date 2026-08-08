# aixue-math

**小学数学教案生成工作流插件** —— 基于 4 类输入合成高质量课时教案。

## 工作流总览

```
                  合成 (aixue-math:generate)
┌─────────────┐           │
│ (1) 教材     │           ▼
│ (2) 知识点   │  ───▶  ┌────────┐
│ (3) 写作要求 │        │ 课时教案 │  ──▶  (aixue-math:refine 迭代)
│ (4) 教案样例 │  ───▶  └────────┘
└─────────────┘
```

一个**课时**对应一个**工作区**。工作区目录如下：

```
workspaces/<NN>_<课时名>/        目录带两位序号前缀（例 01_周长_什么是周长），
│                                由 init 的 next-seq 单调分配；workspace.yaml
│                                的 name 存不带序号的纯课时名
├── .aixue/workspace.yaml        工作区元数据
├── 01_教材/                     输入 (1)
│   ├── docs/                    原始 PDF
│   └── extracted/               aixue-math:textbook 产物
├── 02_知识点/                   输入 (2)
│   ├── docs/                    参考书原件
│   └── extracted/               aixue-math:knowledge 产物
├── 03_写作要求/  → shared/03/   输入 (3)（软引用全局资源）
├── 04_教案样例/  → shared/04/   输入 (4)（软引用全局资源）
├── 05_教案/                     输出 (5a) 教案
│   ├── md/                      Markdown 源（每课时最新版）
│   ├── docx/                    Word 副本（最新版）
│   ├── html/                    图文 HTML（最新版）
│   ├── pdf/                     印刷 PDF（最新版）
│   └── OLD/                     历史版本（md/docx/html/pdf 镜像）
└── 06_板书/                     输出 (5b) 板书（与教案平级）
    ├── render.py                HTML → PNG 渲染器（一份服务所有课时）
    └── 课时N/                   每课时一目录
        ├── infographic.html     单张大图
        ├── slide-deck.html      多页逐屏
        ├── png/                 当前版渲染输出 PNG
        └── OLD/                 历史版本 PNG
```

> **无 draft/final，最新版当面**：`05_教案/{md,docx,html,pdf}/` 各只放每课时最新版，历史自动降级到 `05_教案/OLD/`；`workspace.yaml` 用 `current_version` 记版本号。板书同理（`课时N/png/` 当前版、`课时N/OLD/` 历史）。

## Skills 一览

| Skill | 角色 | 状态 |
|-------|------|------|
| `aixue-math:init` | 初始化课时工作区 | ✅ 可用 |
| `aixue-math:textbook` | 输入(1) 教材 PDF → 结构化 Markdown | ✅ 可用 |
| `aixue-math:knowledge` | 输入(2) 知识点提取 | ✅ 可用 |
| `aixue-math:generate` | 合成 4 输入 → 教案初稿 | ✅ 可用 |

`refine`（教案定向修订）/ `status`（工作区进度）/ `next`（智能引导）尚未实现，见路线图。

## 路线图

- **v0.1** 骨架 + `init` + `textbook` ✅
- **v0.2** `knowledge` ✅
- **v0.3~0.5** `generate`（核心）+ 源产分离 + 课时序号前缀 ✅
- **v0.6** `status` + `next`
- **v0.7** `refine`
- **v1.0** 稳定版

> 当前为 **0.5.x 预览版**，四个已实现 skill 可用于完整的「教材 → 知识点 → 教案」链路；接口仍可能调整。

## 跨项目复用说明

本插件为**公共发布版**，不绑定特定项目路径：

- 工作区路径由用户在调用 `aixue-math:init` 时指定，或通过 CWD 自动发现 `.aixue/workspace.yaml`
- `shared/` 目录路径由 `workspace.yaml` 中的 `shared_dir` 字段配置
- Skill 内部通过 `Glob("**/plugins/aixue-math/**")` 等方式动态定位自身资源

## 未来扩展

架构设计支持扩展到其他学科（语文、英语、科学等），每个学科独立一个 plugin（如 `aixue-chinese`、`aixue-english`），共享相同的工作流设计哲学与 workspace 规约。
