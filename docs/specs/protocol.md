# 教学协议

模型在规划、前置检查、逐节教学时遵守的规则，以及这些规则怎样加载。实现：入口 `plugin/skills/learn/SKILL.md`（约 50 行：技能目录、工作区判断、信任边界、四种模式、启动判断、教学入口）；`references/` 下按需读取的 `hosts.md`（各宿主的路径）、`workspace.md`（布局）、`store.md`（知识库命令与硬约束）、`build.md`（建课 §1–§5 与默认值）、`stages/`、`prerequisite/`、`protocol/`；评测在 `plugin/evals/`。本文是这些文件的索引与摘要，规则原文以它们为准。

## 1. 加载规则

- 协议按阶段和状态拆成小文件，模型只读当前阶段或状态对应的那一份，不一次读完整个目录。`protocol/` 下最长的文件 52 行。
- 一次回复只推进一个状态；提问或追问后把对话交还学习者，不同时回答自己的问题。
- 凡能用 schema、文件边界或校验器表达的约束，不写成提示词。真实运行里出过的错进校验器：URL 当本地路径、supporting 无验收题、`outline_confirmed_at` 午夜占位、探测题混进 unit 文档、unit 里的"验收 X"提醒。
- 阶段之间的接口是文件：`learner-profile.md`、`materials-survey.json`、`learning-plan.md`、`lesson-plan.json`、`learning-progress.json`、知识库。

| 时刻 | 读取 |
|---|---|
| learn 启动 | `stages/_index.md`（判断顺序） |
| 阶段 1–4 | `stages/profile.md`、`triage.md`、`plan.md`、`outline.md`；骨架课 `skeleton.md` |
| 前置检查 | `prerequisite/_index.md` → `diagnose.md`、`supplement.md`、`bridge.md` |
| 骨架课：units 生成后、第一个 READY 前 | `protocol/probe.md` |
| READY / PREDICT / DEEPEN / MAIN / ASSESS / 反馈 / resume / 记录 / 结课 | `protocol/` 同名文件；总表在 `protocol/_state-machine.md` |

## 2. 规划阶段

启动时静默判断：有未完成的 `learning-progress.json` → resume；无 `whetstone/learner-profile.md` → 阶段 1；材料是目录、多路径或 > 30 KB → 阶段 2、3；本课无 `lesson-plan.json` 或 `outline_confirmed_at` 为 `null` → 阶段 4（档案 `orientation: domain` 且这门课是骨架课 → `skeleton.md`）；否则阶段 5。每阶段只问一个问题；熟手一轮就见到第一道题，新手最多三轮；其余用默认值并在产物里标"默认值，可修改"。

| 阶段 | 规则 |
|---|---|
| 1 目标与背景 | 一次问完最多四项：情境与取向、相关背景、终点能力（写成可验收的行为）、约束与偏好（默认深度、前置策略、知识库、每周时间）。已有档案只增量更新，不覆盖手写内容。背景自述只供参考，不当能力证明 |
| 2 材料评估 | `survey_materials.py` 只读目录、文件名、大小、日期和文本前 4 KB。四级 A / B / C / D；B 与 C 的边界必须问学习者；会话记录只有学习者本人参与过才算材料，且仍是 C 级。问目的：学上游、巩固自己做的、接手别人的——决定哪一级进课程。切分的数字（≤ 30 KB、4–8 节等）是建议值，不进校验器；同一内容多个版本只取一个 |
| 3 学习计划 | 先列全部候选课程的表，再一门一条消息确认，学习者可说"后面的都接受"；候选 ≤ 3 门可一起确认；被删的课程移到"暂不学"并保留理由；不在此阶段出任何大纲；C 级不进任何课程的来源 |
| 4 大纲 | 范围 → 抽概念并标角色 → 覆盖表 → 校验 → 呈现（目标与范围、问题链、全部概念、`excluded` 及理由、预计规模）→ 只问一件事（模式 + 略过 / 加深 / 升级）→ 写回 `mode`、`deferred[]`、`outline_confirmed_at`（`date -u +%FT%TZ` 取真实时间）→ 再校验。确认前不生成任何 `units/`。学习者说"你定"= 完整、不略过。已有确认过的大纲时是修改模式，只改要改的部分 |
| 5 生成与教学 | 每个非 deferred 的节一份 `units/<id>.md`，独立生成、逐份校验；`learning_state.py init`；前置检查或探测轮；逐节教学 |

## 3. 前置检查

`prerequisite_check`：`auto`（默认，材料依赖了课程内不解释、且会阻断主线的知识，而学习者背景未知时才做）、`always`（学习者自述基础薄弱时档案里记这个）、`skip`。骨架课不跑这一阶段，改为探测轮；探测暴露地板太低时进入同样的诊断与建课。三个触发点：前置检查或探测轮之后、大纲确认时学习者说"我不懂 X、Y"、正课中途暴露缺口（只诊断受影响的簇）。

1. **最小前置地图**：只列会阻断主线的概念簇，记名称、为何是前置、支撑哪段主线、材料位置、确定性，可选 `dependency_kind`（`def` 缺定义、`mech` 缺机制、`tool` 缺表征或操作）；写 `prerequisite-plan.json`，`validate_prerequisites.py` 校验。开启知识库时先 `index_match.py prerequisites --lesson-id <本课>`，按 `variant / variant_then_diagnose / diagnose` 处理（见 [knowledge-store.md](knowledge-store.md) §3）；本课的前置课里学过的概念一律 `variant`。
2. **诊断**：一次一题，提问后交还对话，不给参考答案；问题优先暴露能否生成概念、说明边界、说明关系与方向、应用到新情境；对每个簇记 `ready / fragile / gap / misconception / skipped` 与判断置信度；证据够就停，不凑题数；`prerequisite_state.py` 追加原始回答，开启知识库时同时记 `kind: diagnostic`。只说"这个簇对本材料尚未就绪"，不作能力概括。`build + teach` 模式下写完计划、提出第一题就停。
3. **建前置课**：先按 `dependency_kind` 分流——`def` 不建课，写进父课当前节的 `listed` 概念；`mech` 建课；`tool` 建课但每节主问题改为"做一遍"，判定看结果——对需要建课的簇建一门课（簇多、有依赖时按依赖拆成几门串成栈）。来源按外部存档规则检索、存档、整目录作 `pool`；`lesson-plan.json` 写 `schema_version: "1.4"`、`prerequisite_of`、`blocked_at`、`depth`，`mode` 与父课相同；每节"当前问题"用删除思想实验；`final_challenge` 出成靠近父课材料的桥接题。父课 `learning_state.py block --section-id <blocked_at> --by <本课>`；学习计划的"前置栈"加一行。之后与普通课程完全相同：确认大纲、生成 units、逐节教学、记录。前置课自己暴露缺口时同一协议递归。
4. **回程**：前置课结课后登记概念、重建掌握状态、`unblock` 父课、更新前置栈、报告回到父课哪一节。父课 resume 时对被卡簇各出一道变式题（知识库：`kind: variant`，隔夜再答才算延迟证据；未开知识库：`prerequisite_state.py bridge`），答错的簇不再建课，给一个针对性追问后继续；然后从 `blocked_at` 那节的 READY 继续。学习者中途放弃前置课时 `unblock` 父课并在栈里标"未完成"，不清零记录。

小缺口也建课，不再生成 `prerequisite-guide.md`（旧课程的这份文档校验器仍接受）。

## 4. 逐节教学

```text
READY ─ 只揭示 problem，请学习者预测 → PREDICT ─ 揭示 solution 与 mechanism，对照预测一句 → MAIN
MAIN ─ 问是否细化本节（DEEPEN）→ 说把握（有把握 / 没把握 / 不知道）→ AWAITING_ATTEMPT
ASSESS ├ mastered → 简短巩固，下一节 READY
       ├ partial  → 一个针对性追问 → AWAITING_RETRY
       ├ retry    → 证据纠正 → AWAITING_RETRY
       ├ skipped  → 下一节
       └ paused   → 保存位置
```

每一轮先运行 `next_step.py --progress <进度文件> [--store <库>] [--resume]`：它从进度文件判断状态——`BLOCKED`（等前置课）、`FINISH`（全部完成）、`PROBE`（骨架课未记 `probe_completed` 事件）、`AWAITING_RETRY`（最近判定是 `partial / retry`）、`READY`（本节还没作答）——打印该读的那一份协议文件和填好路径的命令；进度文件超过 1 小时未更新或加 `--resume` 时先给 resume 开场。本节数据用 `lesson_section.py <lesson-plan.json> --section <id>` 取（问题、方案、机制、新问题、概念、主问题、判定标准、提示、意义、取舍、思想、探测题），`--final` 取结课题、分支候选与打乱顺序的概念名，`--list` 列全部节；模型不整份读 `lesson-plan.json`。探测轮结束记 `learning_state.py mark --type probe_completed`。

**READY**：只呈现 `problem`，问"你觉得应该怎么解决"或"难点在哪"。学习者已读过本节、节太短、学习者要求加快时跳过 PREDICT 直接进 MAIN。

**PREDICT**：收到预测后，本节 core 概念带 `cases` 时先并列两个案例请学习者写共同结构，再呈现 `solution` 与 `mechanism`，一两句对照异同；带 `contrast` 的概念揭示后点出近邻与差在哪个变量。预测与共同结构不判分、不记录。`tradeoffs` 与 `new_problem` 留作主问题和追问的素材。

**DEEPEN**：提出主问题前问一句"本节还有 {listed 概念} 等衍生概念，想先深入哪一个，还是直接回答"，候选取本节 `listed` 概念，没有就不问。学习者选择细化时生成 `zoom/<id>-guide.md`（只覆盖本节衍生概念，每个概念至少两个例子，一个贴材料语境、一个换情境；来源约束同讲义；不含本节 checkpoint 的答案），读完回到本节主问题；一节最多细化一次；不在建课阶段预生成。

**MAIN**：主问题要求两到三项——用自己的话解释、说明前一步为什么不足、描述输入如何变输出、指出关系与理由、给例子或失败条件、预测移除某组件的后果；不问"你理解了吗"、判断题、能从标题抄出的答案。作答前请学习者说把握：有把握 / 没把握 / 不知道，记录为 `--confidence 5 / 3 / 1`，不愿标注不坚持。学习者说"验收 X"且 X 是本节或已完成节的 `supporting` 概念时，用 `check.prompt` 出题，按 ASSESS 评估，记 `--kind supporting --concept <id>`，不加 `--progress`，追问最多一层。

**ASSESS**：按 `criteria` 的含义判，不看措辞；分别看核心问题是否识别、机制是否因果连贯、前后关系是否正确、边界或代价是否理解、有无高信心误解、新增联系是否有依据。`verdict`：`mastered`（核心概念与关系已解释清楚）、`partial`（主线对但缺一项重要机制或关系）、`retry`（有会影响后续理解的误解）、`skipped`。`depth_reached` 与 verdict 分开：取回答自发到达的最高层，追问引导后才到达的记在追问那次；同时记满足的 criteria id。怀疑参考本身有错时暂停判分，回到来源，标为材料或参考不确定。开启知识库时判定前先写抽取 JSON，`lrg_record.py append --extraction` 调用比较器，按 `feedback_priority` 的顺序反馈。

**反馈**：先指出确实正确的具体内容；一次只处理一个问题，高信心误解优先于最重要的遗漏；给一个最小提示、反例或证据定位，或从六种追问里选一种——边界（"什么情况下 X 会失效"）、反例、因果深挖（"A 导致 B，中间发生了什么"）、删除思想实验（"把 X 拿掉哪里最先出问题"）、对比（"X 和 Y 都能做到，材料为什么选 X"）、重新归类（"X 不是一个东西，是一个过程——按过程再说一遍"，只在回答与参考冲突且两边 `ontology` 不同时用）。追问由本次回答驱动，不照抄题库；同节最多两层，之后给完整解释并要求学习者用新表述总结。同节不重复出相似题：要再验证就换更高认知层级的问题，或留给 resume 的变式题。低信心但正确的明确肯定。

**快速模式**（`mode: fast`）：评估维度与 `depth_reached` 不变，判定放宽一档——方向对、缺细节记 `partial`，给一句修正（带定位）直接下一节，不追问；只有会断掉后续因果链的误解才 `retry`，最多一层追问。高信心错误仍要指出。记录带 `--rigor fast`。

**记录**：每次产生 verdict 都记录。不开知识库：`learning_state.py record --state … --section-id … --response-file … --verdict … [--confidence] [--criteria-met c1,c3] [--depth …]`，只追加，不覆盖首次回答。开知识库：`lrg_record.py append`（字段见 [knowledge-store.md](knowledge-store.md) §4）。两个命令都拒绝同一节里回答原文相同的记录（`--force` 才追加），回填用 `--at`；每节用时由脚本按与上一条记录的间隔算。

**resume**：先不进未完成的节。从已完成的节里选一个概念出一道变式题——换情境或换角度考同一机制，禁止复用原 `checkpoint` 措辞；作答记 `record --review`（知识库：`--kind review`），当前位置不变；变式失败的节回到 `in_progress`，在后续节完成后再重做。开启知识库时先 `learner_state_build.py build`，再按 `review_pool.py` 给出的顺序取题：假性掌握的概念 → 匿名命题（"有一种说法是「…」。这个说法哪里有问题？"——不说是学习者自己说的，不引用原文，纠正在同一轮给出）→ 链重建漏掉的边（"X 和 Y 之间是什么关系"）→ 过期的概念。然后一两句重建上下文，进入未完成节的 READY。

**探测轮**（骨架课）：见 [domain-skeleton.md](domain-skeleton.md) §5。

**结课**：先链重建——只给 `lesson_section.py --final` 打出的打乱概念名，学习者写出谁引出谁、谁依赖谁、哪几个属于同一节，抽成 `relations[]` 记 `lrg_record.py append --kind final --chain`，反馈只说漏了哪两个概念之间的关系、哪条方向反了、哪条类型不对，不展示参考图；再解释删除或替换某组件的后果；在新案例里应用同一机制；标出仍不确定的关系。快速模式第一项必做，标准是"能把节之间的问题 → 方案串起来、说出关键取舍的方向"，链重建比例只记录不设阈值，其余可选，并写明略过的节。总结分开报告"已解释成功""提示后成功""仍待复习""材料本身不确定"，注明本课内的成功多为即时证据。开启知识库时迁移题记 `--kind transfer`，结束后 `learner_state_build.py build`。骨架课多一步分支决策。

## 5. 评测

`plugin/evals/materials.json` 固定三份材料：一份文档（`evals/materials/learning-layers.md`）、一个小代码库（`learning_state.py`、`mrg_export.py`、`comparator.py`）、一篇评审（`evals/materials/evidence-review.md`），各带学习目标和期望范围（节数、每节概念数、关系数）。用技能建课后：

```bash
python3 evals/score_pack.py <课程目录> --sources-root <材料根> [--store <目录>] [--material-id <id>] [--baseline 上次.json] [--output 本次.json]
```

建课指标：校验错误与警告数、节数、每节概念数、`support` 分布与 `unsupported` 比例、关系数、各层概念数、每节 criteria 数、locator 命中率、模式、角色分布、覆盖表各去处计数、deferred 数、units 是否齐全。教学指标（给 `--store` 时从 LRG 读）：作答数、各 `kind` 与 `verdict` 计数、`depth_reached` 分布、主问题用时中位数。`--baseline` 逐项打印差异。`results/example-baseline.json` 是示例课程目录的一次打分。提示词或协议的改动应在同一组材料上看到指标变化。
