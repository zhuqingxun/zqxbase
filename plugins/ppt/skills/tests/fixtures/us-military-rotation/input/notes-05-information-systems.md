---
description: "研究笔记 05: 信息系统与流程标准化"
status: completed
module: 5
created_at: 2026-04-20T00:00:00
updated_at: 2026-04-20T00:00:00
---

# 模块 5 研究笔记：信息系统与流程标准化

## 一、美军官员调动的 3 大核心系统

### 1. AIM 2.0（Assignment Interactive Module 2.0）
- **上线**：2016 年 12 月试点，2019 年全面铺开
- **功能**：双向 marketplace，officer 与 unit 互排
- **访问**：军官用 CAC（Common Access Card）登录
- **数据**：KSBs + OER + 偏好清单

### 2. IPPS-A（Integrated Personnel and Pay System - Army）
美军**总集成的人事+薪酬平台**，对标企业的 SAP SuccessFactors：
- **目标**：把分散的 40+ 遗留系统整合为一个
- **范围**：现役 + 后备 + 文职 共约 100 万人的人事数据
- **全面上线**：2023 年（经历多轮延期）
- **功能**：
  - 人事档案（性能、履历、健康、家庭）
  - 薪酬发放
  - 训练记录
  - PCS 订单生成
  - 与 AIM 2.0 对接传递匹配结果

### 3. MyAssignments
军官侧的轻量级前端：
- 查看当前 PCS 订单状态
- 更新个人偏好
- 与 career manager 沟通
- Mobile-friendly

## 二、一次调动的完整流程节点

基于多源拼接（Capt. Travis Salley 亲历 + ATAP 官方指南）：

| 节点 | 时长 | 主要动作 |
|------|------|---------|
| **T-12 个月** | — | Career Manager 识别需要 PCS 的军官清单 |
| **T-11 月：Cycle 开放** | Day 1 | AIM 2.0 marketplace 发布所有 vacancies |
| **T-11～T-9 月：Marketplace 窗口** | ~21 天 | Officer 排序 + Unit 排序 + 双向面试 |
| **T-9 月：Algorithm Run** | 数天 | Deferred acceptance 算法匹配 |
| **T-9 月：Match Release** | Day 1 | Match 结果公布，Career Manager 审查 |
| **T-8 月：PCS Order 生成** | ~7 天 | IPPS-A 生成正式订单 |
| **T-7～T-0 月：准备期** | 7 个月 | 搬家、训练、交接 |
| **T-0：Report Date** | — | 军官到新单位报到 |

**总计约 11-12 个月**，高度可预测。

## 三、审批链路自动化

### 传统模式（2015 年前）
- Officer 给 career manager 发邮件 → career manager 电话协调 unit → 人工填表 → 多层签批 → 纸质订单
- **总时间**：不可预测，**失败率高**
- **决策不透明**：officer 不知道自己的偏好是否被考虑

### AIM 2.0 + IPPS-A 模式
- Officer 在 AIM 2.0 排序，数据直接进入匹配引擎
- Algorithm 自动运行（无人工干预）
- IPPS-A 自动生成 PCS 订单
- **总时间**：可预测
- **透明度**：officer 可在 portal 实时看到排名、匹配状态

### 具体数字（Eightfold.ai 报道）
2019 年 ATAP 首次 cycle：
- 15,000 名军官参与
- 50%+ 获 first choice
- 80% 获 top 10 内

## 四、数据驱动决策

### 人才档案结构（DTIC Technical Report 1421：Army Talent Attribute Framework）
每位军官的档案包含：
- **K**nowledge：教育背景、军校、专业证书
- **S**kills：语言、专业技能、认证
- **B**ehaviors：OER 评估、360 反馈
- **P**references：工作地点、兵种、职业方向偏好

### 数据如何被使用
1. **匹配**：ATAP algorithm 用 KSB-P 做 officer-to-job 匹配
2. **选拔**：晋升板用 KSB 做比较
3. **规划**：HRC 用整体人才池数据做 Force Shaping 决策

## 五、Force 2025 CONOPS（Talent Management Concept of Operations）

2019 年 Army 发布《Talent Management Concept of Operations for Force 2025 and Beyond》，核心框架：
- **Acquire**：获取人才（招募与 assession）
- **Develop**：发展人才（training + broadening + education）
- **Employ**：使用人才（ATAP 分配）
- **Retain**：保留人才（retention policies）

四个阶段共享同一数据基础设施（IPPS-A）。

## 六、三个企业痛点的映射

### 痛点 1：个体意愿 vs 组织需求
- **美军机制**：IPPS-A 持久化保存每位军官的 K-S-B-P，算法自动对齐需求与偏好
- **企业映射**：企业需要"员工人才档案"统一数据库——不是 HR 系统里分散的简历字段，而是结构化的 KSB-P

### 痛点 2：部门保护主义 vs 公司整体意愿
- **美军机制**：所有数据在 HRC，不掌握在 unit 手里——原部门无法隐藏、篡改、延迟数据
- **企业映射**：员工档案与绩效数据必须归集团人力中台，业务单位只有"可读"权限

### 痛点 3：调动成本与效率
- **美军机制**：一次 PCS 从 cycle 开放到报到 11-12 个月、流程 100% 数字化
- **企业映射**：数字化审批链路 + 固定的 cycle 时间窗口 = 可规划的人才流动节奏

## 七、对标 IBM 的数字化人才管理

IBM 的 Watson Candidate Assistant + Your Learning 平台：
- AI 驱动的内部职位推荐
- 技能图谱（skills graph）——对标军方 KSB
- 预测性分析识别高潜力人才
- Blue Opportunities 内部市场——对标 AIM 2.0

**IBM 2024 数据**：
- 50% 空缺职位通过内部市场填充
- Your Learning 平台支撑 345,000 员工的技能发展

## 八、信息源（本模块核心）

### Tier 1（官方资料）
- Army.mil: Five Things Officers Should Know About AIM：https://www.army.mil/article/221864/five_things_army_officers_and_units_should_know_about_the_assignment_interactive_module
- Talent Management CONOPS for Force 2025：https://talent.army.mil/wp-content/uploads/2019/11/Talent-Management-Concept-of-Operations-for-Force-2025-and-Beyond.pdf
- DTIC TR 1421: Army Talent Attribute Framework：https://apps.dtic.mil/sti/trecms/pdf/AD1190814.pdf

### Tier 2（深度分析）
- Eightfold.ai: How US Army Embraced Data：https://eightfold.ai/blog/army-talent-management/
- Army.mil: Talent Management Milestones：https://www.army.mil/article/244020/new_report_highlights_talent_management_milestones
- DMI-IDA: Critical Review of Literature on Army Talent Management：https://www.dmi-ida.org/download-pdf/pdf/AD1334213_ACriticalReviewoftheLiteratureonArmyTalentManagementwithRec.pdf

### Tier 4（实操经验）
- Army.mil: One Officer's Experience with ATAP：https://www.army.mil/article/229676/one_officers_experience_with_the_army_talent_alignment_process
- From the Green Notebook: Optimizing Talent Management AIM：https://fromthegreennotebook.com/2021/11/15/optimizing-talent-management-recommendations-for-the-next-version-of-the-assignment-interactive-module-aim/
