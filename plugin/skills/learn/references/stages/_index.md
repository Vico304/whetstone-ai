# 规划阶段：入口

`learn` 是总入口，**缺什么补什么**；`guide` 与 `outline` 是从某个阶段重入的壳。阶段协议只在这里维护一份。

| 阶段 | 产物 | 读取 | 什么时候跳过 |
|---|---|---|---|
| 1 目标与背景 | `learner-profile.md`（工作区根，跨课） | [profile.md](profile.md) | 档案已存在且学习者没说要改 |
| 2 材料评估 | `materials-survey.md/json` | [triage.md](triage.md) | 材料是单个 ≤ 30 KB 文件 |
| 3 学习计划 | `learning-plan.md`（课程序列，逐门确认） | [plan.md](plan.md) | 只有一门课的规模 |
| 4 课程大纲 | `courses/<id>/outline.md` + `lesson-plan.json`（`outline_confirmed_at`） | [outline.md](outline.md)；骨架课改读 [skeleton.md](skeleton.md) | 该课已有确认过的大纲 |
| 5 生成 units → 前置（骨架课：原理探测）→ 教学 | `units/`、进度、知识库 | learn SKILL.md §4–§7；骨架课的探测轮读 [../protocol/probe.md](../protocol/probe.md) | — |

判断顺序（learn 启动时静默执行）：

```text
有 learning-progress.json 且未完成 → resume（protocol/resume.md）
无 learner-profile.md            → 阶段 1
材料是目录 / 多路径 / > 30 KB      → 阶段 2 → 阶段 3
本课无 lesson-plan.json 或 outline_confirmed_at 为 null → 阶段 4（档案 orientation=domain 且计划里这门课是骨架课 → skeleton.md）
否则 → 阶段 5
```

参与度上限：熟手一轮就应看到第一道题；新手最多三轮。每阶段只问一个问题，其余用默认值并在产物里标 `（默认值，可修改）`。
