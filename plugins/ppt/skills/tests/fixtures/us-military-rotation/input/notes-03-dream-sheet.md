---
description: "研究笔记 03: dream sheet 与双向匹配 (ATAP / AIM 2.0)"
status: completed
module: 3
created_at: 2026-04-20T00:00:00
updated_at: 2026-04-20T00:00:00
---

# 模块 3 研究笔记：dream sheet 与双向匹配

## 一、术语与系统版本演进

### Dream Sheet
老一代术语，指军官向 career manager 手工提交的"志愿清单"，通常是一张列出偏好地点和岗位的纸。**今天已被 AIM 2.0 / ATAP 取代**，但业内仍习惯用 dream sheet 指代"军官偏好表达机制"。

### AIM 2.0（Assignment Interactive Module 2.0）
- 版本：2016 年 12 月试点启动
- 性质：Web-based 双向市场平台
- 功能：officer 排序单位 + unit 排序 officer + 算法匹配

### ATAP（Army Talent Alignment Process）
- 版本：2019 年正式启动
- 性质：包含 AIM 2.0 在内的完整人才对齐**流程**
- 区别：ATAP 是流程+制度，AIM 2.0 是工具平台

### 两者关系（引用 ClearanceJobs 2019 解读）
> "ATAP 是 market-style hiring system 的统称；AIM 2.0 是 ATAP 的官方 IT 平台"

## 二、Marketplace 机制细节

### 一个 Cycle 的关键数字
根据 ATAP 官方指南（v5，2019 年版）+ Modern War Institute 文章交叉验证：

- **每年 2 个 cycle**（active component officer）
- **每个 cycle 覆盖 6 个月**的移动窗口
- **Officer 提交偏好约 3 周**（marketplace 开放阶段）
- Unit 同步排序 officer

### 参与规模（首轮数据）
**2019 首轮 ATAP 数据**（Army Times 报道）：
- 参与人数：约 **14,500 名** active-duty officers at captain and above
- **6,500+ 人获得 #1 偏好**（约 45%）
- **40% 获得 top 1 匹配**（Army.mil "Five Things" 文章）
- **75% 获得 top 10 内匹配**
- **50%+ 的参与单位获得他们排序过的 officer**

### 2025 年数据（Eightfold.ai 追踪）
- **15,000 名军官**在后续 cycle 中获得分配
- **50%+ 获得 first choice**（top 1）
- **80% 获得 top 10 内分配**

数据明显优于 2019 首轮——系统的"学习曲线效应"。

## 三、Deferred Acceptance 算法（核心机制）

### 算法来源
借鉴自 **Gale-Shapley 稳定匹配算法**（1962 年，诺贝尔经济学奖）——同类算法在医学院住院医匹配、纽约公立学校分配中使用。

### 工作原理（Modern War Institute 解释）
1. 两侧同时提交排序：officer 排序单位，unit 排序 officer
2. 算法寻找"稳定匹配"——没有一对 officer-unit 都愿意互换
3. **军官的最优策略是诚实排序**——即使最爱的单位给你排 #2，你仍应把它排 #1

### 举例（官方文档）
> "如果一位移动的军官最爱的职位是 82nd Airborne Division，而 82nd 把他排 #2，军官仍应把 82nd 排 #1。因为没法保证 82nd 会得到其最爱的候选人（可能正看着 101st）。换言之，通过错报偏好无法获得更好结果。"

### Stability Signal（绿色卫星图标）
AIM 2.0 界面中，unit 表达兴趣后 officer 看到"绿色卫星图标"，但：
> "officers frequently mistakenly believe 绿色图标 = one-for-one match，实际只代表该 officer 在该 unit top 10% 偏好名单中，并非确认"

## 四、两种 Marketplace 模式

### Two-sided Marketplace（主流模式）
- Officer 排序 units
- Units 排序 officers
- 通常在排序前有面试（35% of units say interview is the most important factor）
- 当前主要 cycle 使用此模式

### One-sided Marketplace（2025 试点）
ATAP 25-02 试点——针对 pre-KD active-duty captains：
- 仅 officers 排序 units
- units 不参与排序
- 纯算法按 officer 偏好分配
- 目的：减少低资历 captain 的博弈复杂度

## 五、KSB-Ps（知识、技能、行为、偏好）

### 官方定义
**K**nowledge + **S**kills + **B**ehaviors + **P**references

四个维度共同描述军官的"人才档案"，是 ATAP 匹配的数据基础。

### AIM 2.0 Resume 的价值
多源数据：
- 60% 的官员会填写 AIM 2.0 resume
- **填写 resume 的官员得到 #1 投票的概率高 40%**
- 未填 resume 的官员在 marketplace 明显劣势

## 六、面试与直接沟通

Capt. Travis Salley 亲历案例（Army.mil 报道）：
- 主动联系 battalion commander
- 转发 OER、个人履历、简历、服役意愿
- 对方**直接提供职位**（绕过 marketplace 排序大战）
- 最终结果：**完全获得 #1 偏好**

> 这种直接沟通是 ATAP **鼓励**的——系统设计目的就是让 officer 和 unit 直接互选

## 七、dream sheet 的 4 个常见博弈陷阱（From the Green Notebook）

1. **"热门地点大家都想去"** → Deferred acceptance 算法无法让所有人都如愿，但保证"结果对真实偏好的最优化"
2. **军官不写 AIM 简历** → 直接损失 40% 的 #1 概率
3. **只排热门、不考虑冷门** → career manager 建议排序所有可用职位
4. **不跟 incumbent（在任者）沟通** → 失去最大的信息来源

## 八、三个企业痛点的映射

### 痛点 1：个体意愿 vs 组织需求
- **美军机制**：军官通过 AIM 2.0 表达 KSB-Ps，系统用数学方法**最大化整体匹配质量**（不是单纯遵从任何一方）
- **企业映射**：建立类 AIM 2.0 的内部岗位市场，用算法匹配而非"老板拍板"

### 痛点 2：部门保护主义 vs 公司整体意愿
- **美军机制**：Unit 只能**排序偏好**，不能**扣人**。即使 unit 不想放人，officer 被匹配后必须释放
- **企业映射**：部门的"用人话语权"通过排序偏好表达，而不是"锁住"原有员工

### 痛点 3：调动成本与效率
- **美军机制**：一年 2 个 cycle，每个 3 周 + 算法匹配，把成千上万次调动压缩在可预测的时间窗口内
- **企业映射**：把调动从"随时发起、随时审批"改为"周期性集中匹配"——大幅压缩沟通与决策成本

## 九、信息源（本模块核心）

### Tier 1（官方）
- Army.mil: Your Guide to Talent Alignment Marketplace：https://www.army.mil/article/280742/officers_your_guide_to_the_talent_alignment_marketplace
- Army.mil: Five Things Army Officers and Units Should Know About AIM：https://www.army.mil/article/221864/five_things_army_officers_and_units_should_know_about_the_assignment_interactive_module
- Officer's Guide to ATAP (PDF v5)：https://talent.army.mil/wp-content/uploads/2019/11/ATAP_Officers-Guide_v.5.pdf
- ATAP 官网：https://talent.army.mil/atap/

### Tier 2（深度分析）
- Modern War Institute: Winning in the Marketplace：https://mwi.westpoint.edu/winning-in-the-marketplace-how-officers-and-units-can-get-the-most-out-of-the-army-talent-alignment-process/
- Market Design Blog：http://marketdesigner.blogspot.com/2020/12/officer-assignment-in-us-army.html
- Army Times: Almost Half Match Top Job Choice：https://www.armytimes.com/news/your-army/2019/12/13/almost-half-of-officers-match-to-their-top-job-choice-under-new-system/
- Eightfold.ai: How US Army Revolutionized Talent Management：https://eightfold.ai/blog/army-talent-management/

### Tier 4（一线实操）
- From the Green Notebook: AIM 2.0 Tinder for Talent：https://fromthegreennotebook.com/2019/05/10/aim-2-0-tinder-for-army-talent-management/
- The Field Grade Leader: AIM-ing for the Best Assignment：https://fieldgradeleader.themilitaryleader.com/aim/
- One Officer's Experience with ATAP：https://www.army.mil/article/229676/one_officers_experience_with_the_army_talent_alignment_process
- Center for Junior Officers: Perspectives on AIM 2.0：https://juniorofficer.army.mil/perspectives-on-the-aim-2-0-marketplace/

### Tier 3（视频）
- Army Talent Alignment Algorithm 讲解：https://www.youtube.com/watch?v=9mEBe7fzrmI
