# 阶段三：建前置课

对全部非 `ready` 的簇建**一门**前置课；簇之间有依赖且规模大时按依赖拆成几门，串成栈（`skeleton`/父课 ← depth 1 ← depth 2 …）。每门都是普通课程，走阶段 4 → 5，大纲照常呈现并确认。

## 建课

1. **来源**：前置课几乎全靠外部来源。按 [../source-handling.md](../source-handling.md) 的"外部存档"检索、存档到 `<工作区>/external/<集名>_<日期>/`，整目录作 `pool` 进覆盖表，引用标 `external`。父课材料里能落点的部分照常引用。检索不可用时明确说，请学习者提供资料。
2. **`lesson-plan.json`**：`schema_version: "1.4"`、`shape: linear`、`prerequisite_of: <父课 lesson_id>`、`blocked_at: <父课被卡住的节 id>`、`depth: <父课 depth + 1>`（主课为 0）；`mode` 与父课相同；课程目录与父课同级（`<计划目录>/<lesson_id>/`），id 建议 `<主题>-<depth>`，如 `linear-algebra-min-1`。
3. **切节**：每节一个中心机制及其直接依赖。前置概念多是基础机制，"当前问题"用删除思想实验写——没有它，父课的哪一步最先讲不通——而不是历史上人们卡在什么问题上。概念角色、覆盖表、criteria 照常；约定类内容（单位、名称、形状读法）进 `listed` 或 `fact` 层，不为它们单独立节。
4. **`final_challenge`**：出成靠近父课材料的桥接题——用父课 `blocked_at` 那节的一个具体说法，要求学习者用本课概念解释它。
5. **校验**：`validate_lesson.py` 会打印 `fact ratio`。接近全是 fact 层时告诉学习者：这一层是约定，再往下不该建课；本版本仍按课处理，卡片功能未实现。
6. **父课**：`learning_state.py block --state <父课 learning-progress.json> --section-id <blocked_at> --by <本课 lesson_id>`；开启知识库时 `store_init.py register` 会把关系记进 `store.json`。
7. **学习计划**：在 `learning-plan.md` 的"前置栈"里加一行（栈的写法见 `assets/learning-plan-template.md` §3a），每层写 depth、状态、卡在父课哪一节。

## 教学

呈现大纲时说明：这是为了回到 `<父课>` 第 `<blocked_at>` 节而建的课，栈现在是几层、学完这门就回去。之后与普通课程完全相同：逐节生成 `units/`、`learning_state.py init`、按 [../protocol/_state-machine.md](../protocol/_state-machine.md) 教学、记录。结课按 [return.md](return.md)。

前置课自己也可能暴露缺口——同一协议递归：再建一层。每层结课立刻回程，不在底层多停。
