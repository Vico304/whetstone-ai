# 阶段 4：课程大纲 → `outline.md` + `lesson-plan.json`（确认后才生成 units）

对**一门课**做：范围 → 抽概念 → 大纲 → 校验 → 呈现 → 确认 → 写回。已有确认过的大纲时，本阶段是"讨论与修改"：读现有 `outline.md` 与 `lesson-plan.json`，只改学习者要改的部分，重新校验，更新 `outline_confirmed_at`。

## 生成大纲之前

1. 读 `learner-profile.md`（工作区根的，统一布局下再叠加计划目录里的）与计划目录 `learning-plan.md` 里这门课的条目（材料子集、目标）；
2. 建立来源范围（learn SKILL.md 工作流 §1）；
3. 从大框架建立问题链、给每个 unit 分配全部概念并标角色、填覆盖账本（learn SKILL.md 工作流 §3）；
4. 写 `lesson-plan.json`（schema 1.2，`outline_confirmed_at: null`）与 `outline.md`，运行
   `validate_lesson.py <plan> --outline outline.md [--sources-root <材料根>]`。

## 呈现与确认
大纲生成并通过校验后，**停下**，把下面这些呈现给学习者（直接给 `outline.md` 的路径，并在对话里摘要）：

1. 推断的学习目标与材料范围；
2. 问题链：每个 unit 一行"问题 → 方案"；
3. 全部概念清单（按 unit、按角色）；
4. 覆盖账本里的 `excluded` 项及理由——学习者应该知道什么被明确不讲；
5. 预计 unit 数与深度。

然后**只问一件事**，一段话说完：

> "两个决定请你定：① 模式——**完整**（每个 unit 都预测、重建、追问，core 概念全部进检查点）还是**快速**（只保留主线 unit，回答方向对就给修正继续，最后用整体框架重述验收）？② 上面的 unit 里有想略过或想加深的吗、有想从 listed 升成 core 的概念吗？直接回"完整，就这样"或"快速，略过 4 和 6"都可以。"

学习者回答后：

- 写回 `lesson-plan.json`：`mode`、`deferred[]`（略过的 unit 用 `type: section`，理由写"学习者选择略过"或快速模式默认）、`outline_confirmed_at`（**用 `date -u +%FT%TZ` 取真实时间**，不要写 00:00:00 占位；校验器会警告）；升级的概念改 `role`；
- 快速模式默认略过：非主线的 unit（大纲里标为可略过的）、以及所有 `listed` 概念保持 listed；不擅自略过 core unit；
- 更新 `outline.md` 的模式与状态列，重新校验；
- **确认前不得生成任何 `units/<id>.md`。**

学习者说"你定"时：完整模式、不略过；照常写回并继续。`learner-profile.md` 已写明默认深度时用它作默认，但仍呈现大纲并问这一句。
