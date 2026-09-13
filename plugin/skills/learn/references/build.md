# 建课：从来源范围到 units

`learn` 启动判断（[stages/_index.md](stages/_index.md)）落到阶段 4–5 时读本文。各节编号沿用旧入口的 §1–§5，其他文件引用它们。

## 0. 低输入自动补全

用户明确要用本技能学习一组材料时，不要要求其重复粘贴完整的配置提示词。只要材料可访问且目标足以开始，就按 SKILL.md 的启动判断补齐缺失阶段后继续执行；单个小文件加一句目标即可开课。

工作区里有 `learner-profile.md`（由 guide 维护）时先读取它：情境、背景、终点能力、默认深度、前置策略、知识库开关都从档案取，其字段优先于下述默认值；档案是背景说明，不纳入来源清单与课程内容，其中的背景自述仅供参考，前置诊断仍按 `prerequisite_check` 执行。有 `learning-plan.md` 且本次材料对应其中某门课时，材料子集与目标从计划取。除档案、计划或用户覆盖外，使用以下默认值：

- 模式：`build + teach`；
- 学习目标：从用户描述和材料主题推断，重点是延迟重建知识结构并迁移到新问题，而不是仅完成摘要；
- 材料范围：覆盖支撑主线所需的内容，次要细节放入附录；大型代码库先从入口、主流程和关键模块建立范围；
- 前置检查：`prerequisite_check=auto`；用户明确说缺少前置知识时改为 `always`，明确要求直接学习时改为 `skip`；
- 外部知识：不用外部知识改写原材料的主张。三种情况可以检索可靠的外部来源补充——建前置课、补骨架课的 `no-anchor` 概念、材料只说"是什么"没说"为什么"的机制；检索到的先按 [references/source-handling.md](source-handling.md) 的"外部存档"存进 `<工作区>/external/`，再从存档引用并标 `external`；检索不可用时明确说，请学习者提供，不伪造；
- 输出：在可写工作区中为本次材料创建独立课程目录；若同名目录已有进度，优先识别为继续课程，不覆盖原文件；
- 进度：互动教学且有可写工作区时创建或继续 `learning-progress.json`，保留首次回答和所有修订；
- 节奏：一次只推进一个 LearningUnit，等学习者回答后再评估和继续。

开始时简短告知已推断的学习目标、材料范围和输出位置，但不必要求用户确认。只有材料不可访问、学习目标存在会导致完全不同课程的关键分歧，或输出会覆盖无法安全合并的现有课程时，才停下请求用户决定。

## 1. 建立来源范围

1. 识别来源类型：普通文档、代码库、会话记录或混合材料。
2. 多文件或目录输入且可运行脚本时，执行 `scripts/source_manifest.py <材料…> --base <材料根> --output <课程目录>/sources.json` 建立文件清单、大小、类型和 SHA-256（`base_path` 自动记录材料根相对课程目录的位置）；脚本不会汇总正文，也不会读取敏感文件。
3. 读取足以支撑课程主线的来源，记录稳定定位：文档用文件+标题/页码，代码用文件+符号/行号，会话用导出文件或 session 标识+轮次。
4. 报告实际覆盖范围。搜索不到内容只表示“未在已检查范围发现”，不等于材料中不存在。
5. 需要外部来源时（条件见"低输入自动补全"的外部知识一条）：检索 → 存档到 `<工作区>/external/<集名>_<日期>/` 并写 `_index.md` → 存档目录整个作 `pool` 进覆盖表（`heading: "*"`）→ 从存档文件引用，`support: external`。规则见 [references/source-handling.md](source-handling.md) 的"外部存档"。

处理不同来源时读取 [references/source-handling.md](source-handling.md)。

## 2. 检查并补足前置知识

**骨架课（`shape: skeleton`）不跑前置阶段**，改在 units 生成后做一轮原理探测（[references/protocol/probe.md](protocol/probe.md)）；探测暴露地板太低时同样进入下面的诊断与建课。其余课程根据 `prerequisite_check` 判断是否运行前置阶段。运行时先读取 [references/prerequisite/_index.md](prerequisite/_index.md)，再按其加载表只读当前阶段的文件，并按以下顺序执行：

1. 从原材料抽取会阻断主线理解的最小前置概念簇，建立 `prerequisite-plan.json`；
2. 初始化 `prerequisite-progress.json`，在不显示参考答案的情况下一次询问一个诊断问题（开启知识库时先查索引，前置课里学过的概念直接出变式题）；
3. 根据学习者的原始回答判断当前材料所需的概念生成、边界、关系和应用证据，不扩大为一般能力画像；
4. 有任何 `fragile | gap | misconception` 的簇，就为它们建**一门前置课**（[references/prerequisite/course.md](prerequisite/course.md)）：外部存档作来源、`schema 1.4`、模式跟随本课、大纲照常确认、逐节教学与记录；本课在当前节 `learning_state.py block`；
5. 前置课结课后回程（[references/prerequisite/return.md](prerequisite/return.md)）：`unblock`、对被卡簇出变式题，再从被卡的节继续。

小缺口也建课，不再生成补充文档。前置课自己暴露缺口时同一协议递归；`learning-plan.md` 的"前置栈"随时可见。在 `build + teach` 模式中，前置阶段启动后，首次回复到提出第一个诊断问题为止，不提前生成学习者画像或直接进入正课。在纯 `build` 模式中可生成待作答的前置计划，但必须把准备度标记为未评估，不得伪造回答或背景结论。

## 3. 大纲：从大框架建立问题链，并列出全部概念

先回答以下问题，再组织 unit：

1. 这组材料总体要解决什么真实问题？
2. 系统、论证或代码的边界是什么？输入、关键过程和输出是什么？
3. 最早、最直接的方案是什么？它解决了什么，又暴露了什么新问题？
4. 后续每个组件、概念或决策如何回应前一步的新问题？
5. 哪些内容是关键机制，哪些只是实现细节、例子或尚未验证的设想？

不要按文件顺序机械摘要。课程顺序应优先服务因果理解和先修关系；必要时说明它与原材料顺序不同。

然后为每个 unit 分配**全部**涉及的概念并标角色（`core` 进检查点、≤ 4；`supporting` 会讲、自带可选验收题；`listed` 只列名 + 一句事实层定义 + 定位），并填写**覆盖账本**：材料的每个一级/二级标题去了哪个 unit 的哪个角色，或 `deferred / excluded`（带理由）。**任何抽取到的概念都必须有去处，绝不静默丢弃。** 概念多于上限时降为 supporting 或 listed，不是删掉。

产出 `lesson-plan.json`（schema `1.2`；骨架课与分支课用 `1.3`，`outline_confirmed_at: null`）与 `outline.md`，运行 `scripts/validate_lesson.py <plan> --outline outline.md --manifest sources.json`（材料根从 `sources.json` 推出；没有清单时给 `--sources-root <材料根>`）。**然后停下**，按 [references/stages/outline.md](stages/outline.md) 把大纲呈现给学习者并只问一件事（模式 + 想略过/加深的 unit）。两种模式都要确认；确认后写回 `mode`、`deferred[]`、`outline_confirmed_at`。

## 4. 生成教学包：按 unit 逐份生成

大纲确认后，在同一目录生成：

- `outline.md`：路线图与全部概念清单（已生成，按确认结果更新）；
- `units/<section-id>.md`：**每个非 deferred 的 unit 一份，每份是一次独立生成**——只带该 unit 的来源定位去读原文，长度预算按 unit 计，不受整包限制；宿主支持并行子代理时可并行生成；生成后逐份运行 `validate_lesson.py <plan> --units-dir units/`；
- `lesson-plan.json`：小节、概念角色、关系、来源、检查点、覆盖账本（骨架课：证据池、概念落点、探测题、分支候选）；骨架课的每份 unit 文档末尾列出"这个原理在你的材料里的落点"（来自 `anchor`），且只引用 `pool` 里的 A 级定位；unit 文档的"轮到你"**原样放 `checkpoint.prompt`**，探测题 `probe.prompt` 不进 unit（校验器对两者都检查）；
- `sources.json`：多文件输入时的来源清单；
- `prerequisite-plan.json` / `prerequisite-progress.json`：前置检查产物（条件生成）；缺口建成前置课，是与本课同级的另一个课程目录；
- `learning-progress.json`：进入教学时用 `scripts/learning_state.py init` 创建（deferred 的 unit 自动标为 `deferred`，不计入完成）。

教学过程中还可能按需产生：`zoom/<section-id>-guide.md`（学习者选择细化某节时，候选来自该节的 `listed` 概念）与 `concepts/`（clarify 技能维护）。旧的单文档 `teaching-guide.md`（schema 1.0/1.1）仍被校验器接受，新课程不再生成。

没有文件工作区时，在对话中提供同等内容，并在当前会话维护进度。使用 [assets/outline-template.md](../assets/outline-template.md)、[assets/units-template/s01.md](../assets/units-template/s01.md) 与 [assets/lesson-plan-template.json](../assets/lesson-plan-template.json) 作为起点。

生成前读取 [references/lesson-contract.md](lesson-contract.md)。前置产物运行 `scripts/validate_prerequisites.py`。用户开启了知识库目录时，校验通过后再运行 `scripts/mrg_export.py --store <目录>` 导出分层参考图并 `index_match.py register`。若创建进度文件，分别使用 `scripts/prerequisite_state.py init` 和 `scripts/learning_state.py init`，不要手写覆盖已有尝试。

## 5. 大纲与 unit 文档质量要求

- `outline.md`：学习目标与模式、材料范围、总体问题、系统地图、问题链（每 unit 一行问题 → 方案）、**全部概念按 unit 与角色列出**、覆盖账本摘要、使用说明。不含任何 unit 的机制、意义、代价、criteria、principle。
- `units/<id>.md`：围绕一个可解释步骤，至少包含：当前问题、解决方案、工作机制、它引出的新问题、本节概念（core / supporting / listed 三块都可见）、来源定位和学习者检查点。`supporting` 概念各有一段"它在本节机制里的位置"，不附"想验收它就说……"的提醒（只在 outline 使用说明里写一次）；`listed` 只有名 + 一句 + 定位，**不讲机制**。**意义、代价与设计思想不进文档**——它们写在 `lesson-plan.json` 的 `meaning`、`tradeoffs`、`principle` 里，作为主问题与追问的素材，由学习者在回答中自己得出。
- "新问题"应自然引出下一 unit；最后一个 unit 可转为未决问题、边界或迁移挑战。
- 来源定位靠近相关结论。外部知识必须单独标记，不得用来填补材料缺口而不说明。
- 检查点要求学习者解释概念、关系或机制，而不是只复述句子或回答选择题。
- 快速模式下只保留主线 core unit，其余进 `deferred[]`；被略过的内容在 outline 里可见，日后可补。

## 完成标准（建课与首节教学）

- 课程从总体问题出发，各 unit 形成可追踪的问题—方案链；大纲经学习者确认后才生成 unit 文档。
- 材料的每个标题与每个抽取到的概念都有去处（core / supporting / listed / deferred / excluded），没有静默遗漏。
- 关键结论具有来源定位和支持类型；不确定性没有被流畅措辞掩盖。
- 前置阶段若触发，诊断只量化当前材料所需的准备度；原始回答保留，外部补充可引用且与原材料分层，桥接复测完成后再进入正课。
- 学习者至少被邀请完成第一小节的主动解释；互动模式下一次只推进一节。
- 评估依据概念、机制和关系，原始作答保留。
- 文件模式下，教学包通过结构校验，脚本通过实际执行验证。
