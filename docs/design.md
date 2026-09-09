# Whetstone 设计

本文说明系统为什么这样设计，以及每个设计落在代码的哪里。文件格式见 [specs/](specs/)，学习科学依据见 [reviews/evidence-review.md](reviews/evidence-review.md)，用语对照见 [glossary.md](glossary.md)。本文只描述已实现的行为。

## 1. 问题

传统阅读和普通的 LLM 问答产生同一类失败：看过很多，调用不出。学习者积累的是熟悉感，不是可以解释、可以迁移的心智模型。LLM 让这件事更糟：它能生成流畅的解释，没有来源约束时错误会沉淀为"已学会的知识"；它还能直接总结一个对象的"本质"，但总结一旦展示出来，就变成又一段要背的材料。

所以系统要回答的不是"读到第几页"，而是：学习者现在理解到了哪一层，哪些概念不稳固或已过期，下一次该做什么。

## 2. 立场

学习科学对 desirable difficulties 的结论是：让学习感觉轻松的手段大多损害长期保持，让检索变费力的手段大多增强它。由此四条立场：

1. 不做摘要器。"文件 → 摘要 → 闪卡"是立项时明确避开的形态。
2. 学习者的重建是核心学习行为：隐藏参考，用自己的话解释概念、说明关系；先预测，后揭示。
3. 高层理解不可传递，系统只创造条件：不展示 rationale 与 principle，靠顺序、问题和重复遇见让学习者自己到达。
4. 学习效果优先于图谱完整和自动化程度。

## 3. 四层与两样不展示的东西

| 层 | 学习者能做什么 | 展示 |
|---|---|---|
| `fact`（事实） | 知道术语、定义、事实 | 是 |
| `mechanism`（机制） | 说清输入如何变成输出，部件如何相互作用 | 是 |
| `rationale`（本质） | 说清为什么这样设计：取舍、代价、回应了什么问题、换掉会怎样 | 否，只用于出题与评估 |
| `principle`（思想） | 把设计思想从对象上剥离，在别处认出它 | 否，只用于出题与评估 |

前两层是显性知识，可以写下来、读到、复述。后两层可以被示范，不能被交付。模型完全能总结出一个对象的本质，但展示给学习者的那一刻，它就降为第一层材料。Schwartz & Bransford 的实验说明了顺序的作用：先对比案例、自己挣扎，之后的讲解被理解为洞见；顺序反过来，同一段讲解只被当作事实记住。

系统对后两层的全部职责是：

- **顺序**：每节先只给"当前问题"请学习者预测，再揭示方案与机制；本质与思想不作为讲解出现。
- **问题**：主问题和追问的素材来自 `lesson-plan.json` 每节的 `meaning`、`tradeoffs`、`principle`。取舍与对比类追问针对 rationale，"把 X 拿掉哪里最先坏"逼近本质，结课的迁移题针对 principle。
- **记录**：每次作答记录 `depth_reached`。同一概念作答链上层次如何爬升，是理解在不在生长的证据。`depth_reached` 不进掌握估计。

两样不展示的东西：

**MRG 的高层。** 渲染出来的文档只含 fact 与 mechanism：`outline.md` 不含任何一节的机制、意义、代价、`criteria`、`principle`；`units/<id>.md` 不含 `meaning`、`tradeoffs`、`principle`、`criteria`。校验器把 criteria 与 principle 的泄漏记为错误。开启知识库时，`mrg_export.py` 把 rationale / principle 层的节点、边和每节的意义、代价、思想、检查标准导出到单独的 `.deep.json`；讲义、概念笔记、学习者查询只读公开文件，高层文件只在评估与出题时加载。

**LRG。** 学习者不能改：否则它退化为"把回答改成正确答案"，摸索过程被抹平，而摸索过程是它的全部价值。学习者不能看：看旧回答没有直接好处，还引入对自身表现的评价情绪。但对自己错误的解释是高价值活动——高信心错误被纠正后记得比一开始就对的更牢——所以旧回答里的错误主张以匿名命题回来："有一种说法是……这个说法哪里有问题？"三条规则：不说这是学习者自己说过的；不展示、不引用原始回答；纠正在同一轮给出。

## 4. 三种记录

### 4.1 SEL：来源

- `sources.json`：`source_manifest.py` 生成的文件清单——路径、类型、大小、SHA-256。不复制正文，不读疑似敏感文件。
- `source_refs[]`：每节、每个概念、每条关系带 `{path, locator, support}`。locator 以标题原文或符号名开头，脚本能核对（`score_pack.py` 的 locator 命中率）。
- `support` 五类，可信度递减：`explicit`（原文明示）> `entailed`（局部可推出）> `external`（外部知识，path 用 URL，带访问时间，不进 `sources.json`）> `pedagogical_inference`（教学组织推断）> `unsupported`。教学推断不得写成原文明示；`unsupported` 不作稳定知识。
- 材料分四级：A 一手（上游源码、官方文档、规范、教材）、B 自著且已核实、C AI 生成的中间文档、D 噪声。C 级永不作来源。

### 4.2 MRG：参考图

- `lesson-plan.json` 是一门课的 MRG，按问题链线性化：每节有 `problem`、`solution`、`mechanism`、`new_problem`、`concepts`、`relations`、`checkpoint`（含隐藏的 `criteria`）、`meaning`、`tradeoffs`、`principle`、`source_refs`。
- 概念 id 形如 `cs.tee.enclave`，跨课稳定；带 `layer`、`domain_path`、`aliases`、`role`。
- 关系九种：`is_a`、`part_of`、`depends_on`、`causes`、`enables`、`implements`、`contrasts_with`、`instance_of`、`prerequisite_for`；有方向，各带 `support`；`prerequisite_for` 默认是教学推断。
- 受信领域内（经验证的教材、经核实的 CS 知识）MRG 是评估的尺子。尺子的错来自模型抽取而非材料——关系方向、粒度、把例子当机制——所以来源定位与 support 不省。评估时 `pedagogical_inference` 降权，与它冲突不判学习者错。
- 开启知识库时导出 `mrg/<id>.json`（公开层）与 `mrg/<id>.deep.json`（高层），节点登记进 `concepts/index.json`。

### 4.3 LRG：学习记录

- 不开知识库：`learning-progress.json` 每节 `attempts[]` 只追加，首次回答与修订都保留；每次记 `verdict`、`confidence`、`criteria_met`、`depth_reached`。
- 开知识库：`lrg/<id>.jsonl` 只追加事件：回答原文、模型抽取（概念状态、关系状态、匿名化的原子命题）、与 MRG 的差异、`verdict`、`depth_reached`、`confidence`、`rigor`、`kind`（`checkpoint / variant / supporting / probe / review / final / transfer`）、`elapsed_seconds`。`lrg_record.py show` 只打印计数与层，不打印原文；原文不进任何面向学习者的输出。
- 抽取是模型对回答的读取，标 `extracted_by: model`；学习者不确认、不修改。异议以新一次作答追加。

## 5. 建一门课

规划分五个阶段，产物寿命不同：

| 阶段 | 产物 | 寿命 | 入口 |
|---|---|---|---|
| 1 目标与背景 | `learner-profile.md`（含 `orientation`） | 跨课 | `guide`、`learn` |
| 2 材料评估 | `survey/materials-survey.md/json`，A/B/C/D 定级 | 一次规划 | `guide`、`learn` |
| 3 学习计划 | `learning-plan.md`，逐门确认 | 一组课 | `guide`、`learn` |
| 4 大纲 | `courses/<id>/outline.md` + `lesson-plan.json` | 一门课 | `outline`、`learn` |
| 5 生成 units → 前置检查或探测 → 教学 | `units/`、进度文件、知识库 | 一门课 | `learn` |

`learn` 是总入口，缺什么补什么；`guide` 与 `outline` 是可重入的阶段入口；阶段协议只在 `learn/references/stages/` 维护一份。每个阶段只问一个问题：熟手一轮就见到第一道题，新手最多三轮。学习目的（学上游、巩固自己做的、接手别人的）必须问。所有产物写在材料根目录下的 `whetstone/`，材料本身不写入。

两个正交的选择在规划时定：

- `mode: full | fast`：一门课的严格程度。快速缩小范围、放宽判定、证据打折，但揭示顺序不变——否则退化为摘要器。
- `orientation: material | domain`：课程范围由材料结构决定，还是由领域的原理结构决定。

**大纲是必经停顿。** 两种模式都要学习者确认后才生成 units。大纲列出问题链（每节一行问题 → 方案）和全部概念及其角色：`core` 进主问题，每节最多 4 个（Cowan 的工作记忆 4±1），超出降为 `supporting`；`supporting` 会讲、各带一道可选验收题；`listed` 只列名、一句事实层定义和定位；`deferred` 略过、日后可补。材料的每个一级、二级标题在 `coverage[]` 里都有去处，校验器对照真实标题检查，遗漏报错。确认后写回 `mode`、`deferred[]`、`outline_confirmed_at`。

**units 逐份生成。** 每个非 deferred 的节一份 `units/<id>.md`，独立生成、只带本节的来源定位读原文、逐份校验。文档含当前问题、方案、机制、引出的新问题、本节概念、来源、主问题；不含意义、代价、思想、criteria。

**前置检查。** 从材料抽出会阻断主线的最小前置概念簇，一次一题、不显示参考答案；只对 `fragile | gap | misconception` 检索可审核来源生成带引用的补充，桥接复测后进正课。正课中暴露新缺口时只对受影响的簇补，不清零课程。

**骨架课（`shape: skeleton`）。** 按领域学时，`coverage[]` 按文件而不是按标题：`pool`（可引用的 A 级材料）、`reserve`（留给分支课）、`excluded`。先画原理依赖图再切节，不设概念数与节数上限。每个 core / supporting 概念填 `anchor`——在材料池里的一处定位，或 `external`、`no-anchor`；校验器打印落点比例，不设阈值。每节一道 `probe`，教学前无提示作答。`branch_candidates[]` 把原理映射到材料模块与实际工作。骨架课不跑前置检查，结课时学习者选分支，每个分支追加为一门 `shape: branch` 的普通课。

**开启知识库时**，建课抽出候选概念后先 `index_match.py recall` 按别名召回，模型判断"同一概念 / 同名异义 / 粒度不同"，拿不准的问学习者，一次最多三个；禁止按名称相似自动合并。校验通过后导出 MRG 并登记。

## 6. 教一节

```text
READY ─ 只揭示"当前问题"，请学习者预测 → PREDICT ─ 揭示方案与机制，对照预测一句 → MAIN
MAIN ─ 问是否细化本节（DEEPEN：生成 zoom/ 文档，读完回来）→ 自评信心 1–5 → AWAITING_ATTEMPT
ASSESS ├ mastered → 简短巩固，下一节
       ├ partial  → 一个针对性追问 → 重答
       ├ retry    → 证据纠正 → 重答
       └ skipped / paused
```

协议按状态拆成文件，模型只读当前状态对应的文件，每份不超过 60 行；一次回复只推进一个状态，提问后把对话交还学习者。

- **预测**只为激活思考，不判分、不记录。
- **主问题**要求两到三项：用自己的话解释、说明前一步为什么不足、描述输入如何变输出、指出关系与理由、给例子或失败条件、预测移除某组件的后果。不问"你理解了吗"、判断题或能从标题抄出的答案。提出主问题前运行 `date +%s` 记本节计时起点。
- **信心**是诊断信号，不参与判定。反馈优先处理高信心且错误的内容；低信心但正确的明确肯定。
- **评估**按 `criteria` 的含义判，不看措辞。`verdict`（`mastered / partial / retry / skipped`）与 `depth_reached` 分开：一个到达 rationale 但有一处事实错误的回答记 `partial / rationale`。取回答自发到达的最高层；追问引导后才到达的记在追问那次。怀疑参考本身有错时暂停判分、回到来源。
- **反馈**先指出确实正确的部分，再一次只处理一个问题：高信心误解 > 最重要的遗漏。追问针对回答实际暴露的最弱一点，从五种里选一种：边界、反例、因果深挖、删除思想实验、对比。同节最多两层，之后给完整解释并要求学习者用新表述总结。
- **同节不重复出题**。要再验证就换更高认知层级的问题，或留给下次 resume 的变式题。
- **快速模式**：`partial` 且方向正确时一句指出对的、一句修正、直接下一节；只有会断因果链的误解才 `retry`，最多一层追问。高信心错误仍要指出。
- **辅助概念验收**只在学习者说"验收 X"时进行，用该概念的 `check` 出题，不影响本节进度。
- **resume** 先从已完成的节里出一道变式题（换情境或角度，考同一机制），作答记为复习、不改变当前位置；变式失败的节回到 `in_progress`，是正常的遗忘信号。开启知识库时可以改从错误命题池出匿名复习题。
- **探测轮**（骨架课）在 units 生成后、教学前：每节一道 `probe`，一次一题，一句话反馈；通过的节列为候选，全部结束后一次性问学习者跳不跳，只有学习者确认才 `defer`。
- **结课**：不看顺序重述整体问题链；解释删除或替换某组件的后果；在新案例里应用同一机制；标出仍不确定的关系。快速模式只有第一项必做。总结分开报告"已解释成功""提示后成功""仍待复习""材料本身不确定"，并注明本课内的成功多为即时证据。骨架课多一步分支决策。

## 7. 跨课与时效

以下只在开启知识库时发生。

- **概念索引** `concepts/index.json`：跨课的概念 id、别名、学科路径、出现记录。对齐靠别名召回加模型确认，歧义问学习者一句；不按名称或向量相似自动合并。
- **变式题代替诊断**：新课前置阶段查索引与掌握状态。`fresh` 的概念出一道变式题代替诊断；`stale` 先变式题、失败再诊断；`unknown` 正常诊断。快速模式留下的 `fresh` 证据按 `stale` 处理。复用因此同时是间隔复习。
- **掌握状态** `learner-state.json` 由 `learner_state_build.py` 从日志派生，随时可重建，不手改。每个概念分开记：最近成功的证据等级（`immediate < delayed < transfer`）、时效、稳定性（成功过的不同日期数）、到达过的层、错误命题、信心校准计数。时效窗口 = 7 × 2^(稳定性 − 1) 天，上限 180 天；只有即时证据记 `unknown`。唯一的标量 `mastery_estimate` = 证据等级权重 × 时效权重，只供可视化着色，不参与任何教学决策。
- **错误复习** `review_pool.py` 只读派生状态，返回匿名化的错误命题；答对后命题仍留在池里，由时效自然淘汰。

## 8. 工程

**用结构换遵循。** 凡能用 schema、文件边界或校验器表达的约束，不写成提示词。教学协议按状态拆文件，任一时刻有效规则不超过 60 行；阶段之间的接口是文件，不是工作记忆；每个阶段附一个范例。校验器把真实运行里出过的错变成规则：URL 当本地路径、supporting 无验收题、`outline_confirmed_at` 写成午夜占位、探测题混进 unit 文档。

**确定性检查交给脚本，语义判断交给模型。**

| 脚本 | 作用 |
|---|---|
| `validate_lesson.py` | 校验 lesson-plan 1.0–1.3、outline、units：结构、角色上限、覆盖表对照真实标题、泄漏、骨架课的 anchor / probe / 分支候选、落点比例 |
| `validate_prerequisites.py` | 校验前置阶段产物 |
| `source_manifest.py`、`survey_materials.py` | 来源清单；混杂目录清点（仓库、文档、生成信号、噪声） |
| `learning_state.py`、`prerequisite_state.py` | 进度文件的 init / record / defer / bridge |
| `store_init.py`、`mrg_export.py`、`index_match.py` | 知识库初始化与登记；导出公开层与高层；别名召回、登记、前置判定 |
| `comparator.py` | 学习者作答抽取对照 MRG：`missing / partial / conflict / weak_reference / representation_only / beyond_reference`，给出反馈顺序，不打分 |
| `lrg_record.py`、`learner_state_build.py`、`review_pool.py` | 追加学习记录；派生掌握状态；取匿名复习题 |
| `scan_wikilinks.py` | 找未解决的 `[[双链]]`（clarify） |
| `evals/score_pack.py` | 给一个课程目录打分：校验错误、概念数、support 分布、locator 命中率、角色与覆盖表指标、每节耗时与 `depth_reached` |

**四个宿主，一份技能目录。** Claude Code 插件、Claude Desktop（`.plugin` 包或 `~/.claude/skills`）、Codex、DeepSeek Harness。技能内路径按 `${CLAUDE_PLUGIN_ROOT}`、`${CLAUDE_SKILL_DIR}` 或技能目录本身解析；Claude Desktop 聊天模式下插件在云端、文件在本地，脚本复制到 `whetstone/scripts/` 本地执行。同一协议在不同模型上的遵循差异本身是数据：Claude 的 locator 命中率 0.145、DeepSeek 0.647（两次真实建课，2026-09-08），由此定下"标题原文或符号名开头"的定位约定。

**测试与评测。** 61 个单元测试；CI 跑测试、校验模板与示例包、知识库全链路冒烟。`plugin/evals/` 固定三份材料，`score_pack.py` 打分；提示词改动要能在同一组材料上看到指标变化。纯标准库 Python，无服务端。

## 9. 不做

- 单一掌握分数（着色标量除外）。
- 让学习者查看或编辑 LRG。
- 展示 rationale / principle 层。
- 对 principle 层作答评分。
- 按名称或向量相似自动合并概念。
- 自研遗忘模型；时效窗口是占位。
- `core ≤ 4` 之外的任何量化上限。
- 把学习者作答当作免费标注。

## 10. 状态

规划管线与建课在 Claude Desktop 和 DeepSeek Harness 上各跑过多次；逐节教学在日常使用中。知识库模式有单元测试和 CI 冒烟，但没有在一门真实课程上留下过学习记录；骨架课在 DeepSeek 上建过一次，探测轮未跑。未经验证的假设列在 [reviews/evidence-review.md](reviews/evidence-review.md)。
