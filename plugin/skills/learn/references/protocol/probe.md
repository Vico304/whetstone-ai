# 骨架课开课前：前置地图与原理探测轮

大纲确认、`units/` 生成、`learning_state.py init` 之后，正式教学之前运行一次。探测之前先做一次前置地图：探测题按规则无提示、原理层、不依赖材料细节，结构上碰不到只在单元正文出现的词，两者各管一段。

## 前置地图（探测之前）

1. 从 `units/` 正文里取出**用来解释机制、而本课 `concepts[]` 没有定义**的概念名。这一步总是做；取到空集就什么都不说，直接进"探测轮流程"。模型专有的字段名（`compress_ratios` 这类）不算概念，它们是材料来源不足的问题。本课有结构讲解节时，那一节安放过的部件也不收——它们的位置由那一节负责讲。
2. 非空时按 `prerequisite_check` 决定诊断到哪一步：`always` 直接诊断；`skip` 只把清单列给学习者、不出题；`auto`（默认）列出清单并问一句"这几个词要不要先测"。
3. 要诊断时按 [../prerequisite/diagnose.md](../prerequisite/diagnose.md) 阶段一写 `prerequisite-plan.json`（只收这些概念），跑 `index_match.py prerequisites`：前置课里学过的出变式题，`unknown` 的出诊断题。
4. 非 `ready` 的簇按 [../prerequisite/course.md](../prerequisite/course.md) 的依赖类型分流：`def` 进本课当前 unit 的 `listed` 概念，由事实卡复习；`mech` 与 `tool` 建前置课，本课在第一个未 deferred 的 unit 上 `block`。建了前置课时 `next_step.py` 报 BLOCKED 而不是 PROBE，按 [../prerequisite/return.md](../prerequisite/return.md) 回程之后再做探测。
5. 前置地图收的是"单元正文用到但本课未定义的词"，探测轮量的是"原理层的地板在哪"。同一个概念不在两处重复出题。

## 探测轮流程

1. 一句话说明规则："每个 unit 一道无提示题，考的是原理不是材料细节；答对可以跳过该 unit，答不对不扣分，直接照学。"
2. 按 unit 顺序，**一次一题**：只给 `probe.prompt`，不给提示、不给材料；学习者作答后交还对话。三种节的探测题不同：
   - 问题链节：原理题，照旧；
   - 过程讲解节：**排序题**——打乱给出这次运行的参与者，请学习者排出先后并说出每步谁做的。答对说明他已经跑通过这条链路，可跳过。判据是 `steps[]` 的顺序与 `actor`；
   - 结构讲解节：**不出探测题**。它的答案就是系统图，而 `outline.md` 里已经印着这张图——探测量不到任何东西。学习者是否已经知道这些部件在哪，由单元生成后的前置地图负责（它抽的正是单元正文用到而本课未定义的概念）。校验器对骨架课的结构讲解节不再要求 `probe`，写了反而报错。
3. 判定：对照 `probe.criteria` 得出 `mastered / partial / misconception`，记录 `depth_reached`。不展开讲解——探测不是教学，一句话反馈即可（"方向对，细节在 unit 2 里补"）。
4. 记录：开启知识库时 `lrg_record.py append --kind probe --section-id <id> --verdict … --criteria-met … --depth …`（即时证据，`rigor` 照常）。
5. `mastered` 的 unit 标为 **skip_candidate**。**不自动跳过**：全部探测结束后一次性列出候选，问学习者"这几个 unit 探测通过，跳过还是照学？"；学习者选跳过的运行
   `learning_state.py defer --state learning-progress.json --section-id <id> --reason "原理探测通过，学习者选择跳过"`，并把它写进 `lesson-plan.json` 的 `deferred[]`（`reason` 同上），更新 outline.md 状态列。
6. 学习者也可以说"全部照学"或"跳过探测"——照办，跳过记 `learning_state.py mark --state learning-progress.json --type probe_skipped`。**档案自述"基础薄弱"时不接受"跳过探测"**：探测量的是地板在哪，不是用来略过的；向学习者说明后照常做。
7. 多数 unit 探测未通过、且学习者表示题目里的术语本身陌生时，不进正课：转 [../prerequisite/diagnose.md](../prerequisite/diagnose.md) 诊断这些簇，再按 [../prerequisite/course.md](../prerequisite/course.md) 建前置课，父课在第一个未 deferred 的 unit 上 `block`。

## 不做

- 不在探测阶段补课或桥接：不通过的 unit 就是要学的 unit；
- 不把探测结果当能力标签：它只决定这门课里跳不跳，知识库里是一次 `probe` 证据；
- 不用探测题替代 unit 的 checkpoint：跳过的 unit 之后仍可通过 resume 的变式检索补证据。

探测轮结束后运行 `learning_state.py mark --state learning-progress.json --type probe_completed`（`next_step.py` 据此不再提示探测），进入第一个未 deferred 的 unit 的 READY。
