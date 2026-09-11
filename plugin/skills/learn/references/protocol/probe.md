# 原理探测轮（仅骨架课）

大纲确认、`units/` 生成、`learning_state.py init` 之后，正式教学之前运行一次。骨架课**不跑** `prerequisite/` 协议——探测就是它的前置判断。

## 流程

1. 一句话说明规则："每个 unit 一道无提示题，考的是原理不是材料细节；答对可以跳过该 unit，答不对不扣分，直接照学。"
2. 按 unit 顺序，**一次一题**：只给 `probe.prompt`，不给提示、不给材料；学习者作答后交还对话。
3. 判定：对照 `probe.criteria` 得出 `mastered / partial / misconception`，记录 `depth_reached`。不展开讲解——探测不是教学，一句话反馈即可（"方向对，细节在 unit 2 里补"）。
4. 记录：开启知识库时 `lrg_record.py append --kind probe --section-id <id> --verdict … --criteria-met … --depth …`（即时证据，`rigor` 照常）。
5. `mastered` 的 unit 标为 **skip_candidate**。**不自动跳过**：全部探测结束后一次性列出候选，问学习者"这几个 unit 探测通过，跳过还是照学？"；学习者选跳过的运行
   `learning_state.py defer --state learning-progress.json --section-id <id> --reason "原理探测通过，学习者选择跳过"`，并把它写进 `lesson-plan.json` 的 `deferred[]`（`reason` 同上），更新 outline.md 状态列。
6. 学习者也可以说"全部照学"或"跳过探测"——照办，记一句到进度事件里。**档案自述"基础薄弱"时不接受"跳过探测"**：探测量的是地板在哪，不是用来略过的；向学习者说明后照常做。
7. 多数 unit 探测未通过、且学习者表示题目里的术语本身陌生时，不进正课：转 [../prerequisite/diagnose.md](../prerequisite/diagnose.md) 诊断这些簇，再按 [../prerequisite/course.md](../prerequisite/course.md) 建前置课，父课在第一个未 deferred 的 unit 上 `block`。

## 不做

- 不在探测阶段补课或桥接：不通过的 unit 就是要学的 unit；
- 不把探测结果当能力标签：它只决定这门课里跳不跳，知识库里是一次 `probe` 证据；
- 不用探测题替代 unit 的 checkpoint：跳过的 unit 之后仍可通过 resume 的变式检索补证据。

探测轮结束后进入第一个未 deferred 的 unit 的 READY。
