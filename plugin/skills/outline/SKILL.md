---
name: outline
description: Generate, discuss or revise the outline of one Whetstone course — the problem chain of units, every concept with its role (core / supporting / listed / deferred), the coverage ledger and the learning mode — and write it back to outline.md and lesson-plan.json after the learner confirms. Use when the learner wants to see, change or redo a course outline ("看看大纲", "把第 3 节拆开", "这个概念升成 core", "改成快速模式"), or to prepare an outline before building. Does not generate unit documents or teach.
---

# Outline：课程大纲

对**一门课**执行 `learn` 技能的阶段 4（生成 / 讨论 / 修改大纲），确认后写回；不生成 `units/`，不教学。

## 输入

- 课程目录（`whetstone/courses/<id>/`）；不存在时按 `learning-plan.md` 里该课的条目（材料子集、目标）新建；
- 已有 `outline.md` + `lesson-plan.json` 时进入**修改模式**：读现有内容，只改学习者要改的部分，保留其余；
- 读 `learner-profile.md` 取默认深度与知识库设置。

## 执行

按 `learn` 技能的 `references/stages/outline.md`（位置见下）：范围 → 抽概念并标角色 → 覆盖账本 → 校验 → 呈现 → 一个问题（模式 + 取舍）→ 写回 `mode`、`deferred[]`、`outline_confirmed_at` → 再校验。档案 `orientation=domain` 且这门课在计划里是骨架课时，改按同目录的 `stages/skeleton.md`：按文件的证据池、原理依赖图切 unit、每个概念的材料落点、每 unit 一道原理探测题、分支候选表；落点比例只展示不设阈值。修改模式下同样以确认结束并刷新 `outline_confirmed_at`。

大纲确认后若 `units/` 已存在且受影响（unit 被拆并、概念角色变化），报告哪些 unit 文档需要重生成，交给 `learn`；本技能不重生成。

## 阶段协议的位置

- Claude Code 插件安装：`${CLAUDE_PLUGIN_ROOT}/skills/learn/references/stages/outline.md`（骨架课：同目录 `skeleton.md`），契约 `${CLAUDE_PLUGIN_ROOT}/skills/learn/references/lesson-contract.md`，校验器 `${CLAUDE_PLUGIN_ROOT}/skills/learn/scripts/validate_lesson.py`；
- 个人技能目录安装：`${CLAUDE_SKILL_DIR}/../learn/...`；
- 其他宿主：与本技能同级的 `learn` 技能目录。

## 边界

- 大纲不含任何 unit 的机制、意义、代价、criteria、principle（校验器会拒绝泄漏）；
- 超过认知负担上限的概念降级为 supporting / listed，不删除；材料每个标题在账本里都有去处；
- 确认前不生成 units；确认是一句话，不做图形化编辑。
