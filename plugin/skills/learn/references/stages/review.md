# 复习课：为学过的课建一门侧重薄弱处的课

学习者说"复习 `<课程 id>`"（可以几门）时进入。复习课需要知识库——它的大纲从掌握状态派生；没开知识库时只有 resume 的开场变式题，说明后照常 resume。复习不是重讲：每节先作答，判定之后才揭示，节文档不得重复被复习节的方案与机制原文。

## 取原料

```bash
python3 scripts/learner_state_build.py build --store <工作区>/store
python3 scripts/review_outline.py --store <工作区>/store --lesson-id <课程 A> [--lesson-id <课程 B>]
```

输出三块：`clusters`——按被复习课的节归簇的薄弱项（假性掌握、最近判定不是 `mastered` 的概念、过期概念、错误命题、链重建漏掉或反向的边），薄弱多的在前；`stable_sections`——每个核心概念至少两次延迟或迁移级成功、且至少一个核心概念到过本质层的节，附它的 `listed` 概念；`reviewed[].pack_dir`——被复习课的目录，节文档从它的 `units/` 与材料取上下文，不复制。

## 大纲

按阶段 4 的流程做，差别只有这些：

1. **节从簇来**：一个簇一节，相邻且有边相连的簇可以合成一节；没有薄弱项的节不进复习课。每节 `review_kind: repeat`、`parent_section: {lesson_id, section_id}` 指向被复习的那一节；`problem` 写成新情境里的问题，优先放在最易与近邻混淆、最易诱发旧直觉的地方（概念有 `contrast` / `cases` 时用它们换情境）；`solution` / `mechanism` 用新情境重述，不抄原文；`checkpoint.prompt` 是变式题，不复用原主问题措辞。
2. **子节**：`stable_sections` 里的节列为可选子节，每个从它的 `listed` 概念或材料池里选一个方向，写成 `review_kind: deepen` 的节（`id` 用 `<原节>.1`），内容是普通 unit（问题 → 方案 → 机制 → 新问题），来源只用材料池与外部存档，不动 `reserve`。**一门复习课最多提供一个子节**，写进大纲但默认不算主线。
3. `lesson-plan.json`：`schema_version: "1.5"`、`shape: review`、`review_of: [<课程 id>…]`、`mode` 跟随被复习课里最严格的一门；覆盖表可为空；`relations[]` 照常写，链重建用它。
4. 呈现确认时多问一句："这次复习 N 节；`<稳固的节>` 已稳定，要不要顺带学它的子节《…》？"学习者不要就把子节 `deferred`。
5. 校验：`validate_lesson.py <plan> --outline outline.md --units-dir units --reviewed <被复习课的 lesson-plan.json>…`——反向泄漏检查在这里。

## 教学时的差别

- 每次会话开始先过到期的事实卡（同 resume：`cards.py due`）。每节 READY 直接提出主问题（读 `protocol/main.md`），作答、判定、反馈之后再揭示 `units/<id>.md`；没有 PREDICT，没有探测轮。`next_step.py` 对复习课打印这个顺序。
- 记录：`repeat` 节记 `--kind review`，`deepen` 节记 `--kind checkpoint`；证据等级由间隔判定，与普通课相同。
- 结课：链重建照常（概念名来自复习课自己的概念）；`review_of` 多于一门时迁移题出成接缝题——一个必须同时用到两门课机制的情境。
- 复习课结课不改变被复习课的进度文件；掌握状态重建后，被复习课下次 resume 的变式题自然反映这次结果。

## 不做

不按固定间隔提醒复习（复习模式：间隔、范围、侧重、一次几个子节——记录，未实现）；不把复习课当第二遍讲义；不为没有薄弱项的课建复习课——直接告诉学习者"这门课没有薄弱项，只有子节可学"。
