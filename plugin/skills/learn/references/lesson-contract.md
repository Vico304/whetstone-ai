# 教学包契约

## 产物

文件模式的标准教学包位于学习工作区 `<材料根>/whetstone/courses/<lesson-id>/`（工作区布局见 SKILL.md）：

```text
<lesson-id>/
├── sources.json
├── prerequisite-plan.json       # 运行前置检查时创建
├── prerequisite-progress.json   # 前置作答、来源与桥接复测
├── prerequisite-guide.md        # 实际暴露缺口时创建
├── lesson-plan.json             # schema 1.2（骨架课 / 分支课：1.3）
├── outline.md                   # 路线图 + 全部概念 + 覆盖账本（取代 teaching-guide.md）
├── units/                       # 每个非 deferred 的 unit 一份，独立生成
│   └── <section-id>.md
├── zoom/                        # 按需细化文档（教学中学习者选择细化时创建）
│   └── <section-id>-guide.md
├── concepts/                    # 概念笔记（clarify 技能维护）
│   ├── _inbox.md
│   └── <概念名>.md
└── learning-progress.json   # 进入教学或需要恢复时创建
```

单一短材料可以省略 `sources.json`，但 `lesson-plan.json` 的 `source_refs` 仍要指向来源。旧课程的单文档 `teaching-guide.md`（schema 1.0/1.1）仍被校验器接受；新课程生成 `outline.md` + `units/`。三个 `prerequisite-*` 文件是条件产物：没有实质前置依赖、学习者近期证据已就绪，或用户选择 `skip` 时可以省略。`zoom/` 与 `concepts/` 是按需产物，build 阶段不预生成。纯对话模式可以不创建文件，但应保持同样的逻辑结构。

## 细化文档契约（`zoom/<section-id>-guide.md`）

- 只在教学中学习者选择细化某节时生成（触发条件见 [protocol/deepen.md](protocol/deepen.md) 与 [protocol/ready.md](protocol/ready.md)），一节最多一份；
- 只覆盖该节内部的衍生概念与机制：每个概念给出"解决什么问题、机制、至少两个例子（一个材料语境、一个新情境）、边界"；
- 不重复主讲义已有内容，不提前讲后续小节，不包含本节 checkpoint 的答案；
- 来源约束与主讲义相同：`explicit / entailed` 用材料内定位，`external` 附出处；
- 概念用 `[[概念名]]` 链接；值得独立成篇的概念交给 clarify 技能写入 `concepts/`，细化文档只保留该概念在本节语境中的角色。

## 概念笔记目录（`concepts/`）

由 clarify 技能维护（契约见该技能的 SKILL.md）。本技能只需遵守：生成的所有文档中允许使用 `[[概念名]]` 双链；不改写、不覆盖 `concepts/` 下已有笔记。

## 前置产物契约

- `prerequisite-plan.json` 只列出会阻断当前材料主线的最小概念簇，并记录它与主材料的依赖与来源定位。
- `prerequisite-progress.json` 是仅限当前课程的证据记录，保留诊断回答、反馈、外部来源和桥接复测；不记录广泛人格或能力标签。
- `prerequisite-guide.md` 只包含实际需要补充的缺口。关键主张需有可点击来源，并标记为 `external`；不得与原材料来源混成一个无区分的“标准答案”。
- 使用 `scripts/validate_prerequisites.py` 校验计划和补充文档，使用 `scripts/prerequisite_state.py` 维护诊断进度。

## `lesson-plan.json`

顶层必需字段：

- `schema_version`：新课程写 `1.2`；校验器与导出脚本同时接受 `1.0` / `1.1`（旧课程）；
- **1.2** `mode`：`full | fast`；`outline_confirmed_at`：大纲生成时为 `null`，学习者确认后写 ISO 时间——为 `null` 时不得生成 `units/`；
- `lesson_id`、`title`、`learning_goal`；
- `source_manifest`：清单相对路径或 `null`；
- `big_picture.problem`：材料总体解决的问题；
- `big_picture.outcome`：学习后应能完成的行为；
- `big_picture.system_map`：从输入到结果的关键步骤数组；
- `sections`：有序教学小节；
- `final_challenge.prompt` 与 `criteria`；
- `uncertainties`：解析、证据或语义上的未决项，可为空数组。

每个 `sections[]` 必需包含：

- `id`、`title` 和只指向更早小节的 `depends_on`；
- `problem`：此处面临的具体问题；
- `solution`：材料采用或提出的方案；
- `mechanism`：方案如何工作；
- `meaning`：它对理解、设计或使用的实际意义；
- `tradeoffs`：边界、代价或失败方式数组；
- `new_problem`：该方案暴露并引向下一节的问题；末节可为 `null`；
- `concepts`：`name` 与面向学习者的 `explanation`；**1.1 另需** `id`、`layer`、`domain_path`，可选 `aliases`；
- `source_refs`：`path`、`locator`、`support` 与简短 `note`。**`locator` 以可机器核对的定位开头**——文档用标题原文（`## Hello World`），代码用符号名（`create_report`）——之后再加描述（`## Flow / ra_config_template.json 的 verify_mr_enclave`）；评测用它的第一段在原文里查找命中率。外部网页用 URL 作 `path`，`support` 必须是 `external`，不进 `sources.json`；
- `checkpoint.prompt`、隐藏评估用 `criteria` 和渐进提示 `hint`；**1.1 中 `criteria` 是对象数组** `{id, text, layer}`，`id` 节内唯一（如 `c1`、`c2`），供 `criteria_met` 引用；
- **1.1 可选** `principle`：本节体现的可迁移设计思想（`principle` 层，只进高层文件，永不进讲义）。

除最后一节外，`new_problem` 应为非空文本。`source_refs.support` 只能是：

```text
explicit | entailed | pedagogical_inference | external | unsupported
```

`unsupported` 只用于记录问题，不得作为稳定讲解的唯一依据。

### 1.1 新增：概念 id、理解层、学科路径、关系

- `concepts[].id`：`<domain>.<concept>` 形式的小写 ASCII，如 `cs.tee.enclave`、`learning-design.macro-map`。跨课程稳定；开启知识库时由概念注册表决定复用还是新建（见 `docs/specs/knowledge-store.md` §4）。同一 id 在多节出现时 `name` 必须一致。
- `concepts[].layer`：`fact | mechanism | rationale | principle`。`fact` 是术语与事实，`mechanism` 是如何工作；这两层可进讲义。`rationale`（为什么这样设计）与 `principle`（可迁移思想）只进高层文件。
- `concepts[].domain_path`：1–4 级学科路径，如 `["计算机科学", "可信计算"]`，属于教学推断。
- 顶层 `relations[]`：概念之间有类型有方向的边，每条 `{id, from, to, type, layer, rationale?, source_refs[]}`。`from / to` 必须是本课程出现的概念 id；`type` 取自 `is_a | part_of | depends_on | causes | enables | implements | contrasts_with | instance_of | prerequisite_for`；`prerequisite_for` 默认 `support = pedagogical_inference`。至少为每节的中心概念写出它与前一节中心概念的一条边。
- `meaning` 与 `tradeoffs` 在 1.1 中语义不变，但归入 `rationale` 层：它们是主问题与追问的素材，**不再渲染进讲义**。

### 1.2 新增：概念角色、supporting 验收、deferred、覆盖账本

- `concepts[].role`：`core`（进主问题与 criteria，每节 ≤ 4，超过 warning——**降级而不是删除**）/ `supporting`（会讲，作为 core 的配角，≤ 6 warning）/ `listed`（只列名 + 一句事实层定义 + 定位，不讲机制，无上限；`explanation` 超过 200 字 warning）。
- `concepts[].check`（仅 `supporting`）：`{prompt, criteria[{id,text,layer}], hint}`，学习者要求"验收 X"时使用；**每个 supporting 概念都要写**（缺失时校验器警告）；criteria 与主 checkpoint 一样不进任何面向学习者的文档。
- 顶层 `deferred[]`：`[{type: "section"|"concept", id, reason}]`。快速模式略过的 unit、学习者选择略过的 unit 都在这里；deferred 的 section 不生成 `units/<id>.md`，`learning_state.py init` 把它标为 `deferred`，不计入完成，之后可补。
- 顶层 `coverage[]`：`[{path, heading, disposition, section_id?, reason?}]`，`disposition ∈ core | supporting | listed | appendix | deferred | excluded`。材料的每个一级/二级标题都必须有一行；`core/supporting/listed/appendix` 需要 `section_id`，`deferred/excluded` 需要 `reason`。`validate_lesson.py --sources-root <材料根>` 会对照真实文件的标题逐条检查。**这是"绝不静默遗漏"的确定性保证。**

### 1.3 新增：课程形态、证据池、落点、探测、分支候选（规格 D）

只有骨架课与分支课写 `1.3`；1.2 的全部规则继续适用。

- `shape`：`linear`（缺省）| `skeleton`（骨架课）| `branch`（分支课）；`parent_course` 仅 `branch` 必需，指向骨架课的 `lesson_id`。
- `coverage[]` 在骨架课里按**文件/目录**记录：`heading: "*"` 表示整个路径；disposition 新增 `pool`（证据池，骨架课可引用）与 `reserve`（留给分支课，`reason` 可选）；`*` 只允许配 `pool / reserve / excluded`。`--sources-root` 对 `*` 路径跳过逐标题检查。分支课与普通课仍逐标题。
- `concepts[].anchor`（骨架课的 `core / supporting` 必需）：`{path, locator}`（`path` 须在某个 `pool` 行之下，`locator` 规则同 `source_refs`）、`"external"`（材料里没有，原理必需）或 `"no-anchor"`（没找到落点；警告，学习者决定）。校验器打印 **grounding** = 有 A 级落点 / 全部 core+supporting，只作 INFO，**不设阈值**。
- `sections[].probe`（骨架课每节必需）：`{prompt, criteria[{id,text,layer}], hint?}`，原理层、无提示；`criteria` 与 checkpoint 一样不进任何面向学习者的文档。
- 顶层 `branch_candidates[]`（骨架课必需，≥ 1）：`{id, title, concept_ids[], materials[], work_relevance?, status: candidate|chosen|declined}`；`materials` 须在 `pool` 或 `reserve` 之下（no-anchor 候选可为空）。`outline.md` 必须列出每个候选的 `title`。
- 骨架课的 `source_refs` 与 `anchor` 只指向 `pool` 里的 A 级材料；`final_challenge` 与迁移题只用学习者的实际材料。
- 不设概念数、unit 数、探测题数上限；`> 9 sections` 的提醒对骨架课关闭。示例：`assets/skeleton-example/`。

## `outline.md`（1.2，取代 teaching-guide.md）

面向学习者的路线图，也是大纲确认阶段呈现的东西。必含：

1. 学习目标、**模式**（及一句含义）、材料范围；
2. 总体问题、系统地图；
3. 问题链：每个 unit 一行"编号、标题、当前问题 → 方案"，deferred 的 unit 标"本次略过：理由"；
4. **全部概念清单**，按 unit 分组、按角色标注（core 只列名；supporting 名 + 一句；listed 名 + 一句事实层定义 + 定位；deferred 名 + 理由）；
5. 覆盖账本摘要：材料各部分 → 去处，`excluded` 附理由；
6. 使用说明：unit 文档在哪、怎么要求验收 supporting、怎么展开 listed、怎么补 deferred。

校验器检查：标题、模式、每个 section 标题、每个概念名都出现；criteria、`check.criteria`、`principle`、`meaning`、`tradeoffs` 都不出现。模板见 `assets/outline-template.md`。 骨架课另需：落点比例、每个概念的落点或 external / no-anchor 标记、分支候选表（校验器检查候选标题）、`probe.criteria` 不出现；模板见 `assets/skeleton-example/outline.md`。

## `units/<section-id>.md`（1.2）

每个非 deferred 的 unit 一份，**独立生成**（只带本 unit 的来源定位读原文）。必含：当前问题、解决方案、工作机制、它引出的新问题、**本节概念**（core / supporting / listed 三块可见；supporting 各有一段"在本节机制里的位置"，**不附"想验收它，说……"之类的提醒**——怎么要求验收只在 outline.md 的使用说明里写一次；listed 只有名 + 一句 + 定位，不讲机制）、来源、"轮到你"检查点。不含 `meaning / tradeoffs / principle / criteria`。校验器检查：文件存在（非 deferred）、标题、检查点（**必须含 `checkpoint.prompt` 原文**）、本节每个概念名；criteria / principle 泄漏为错误，骨架课 `probe.prompt` 出现在 unit 里为错误（探测题在教学前无提示作答，不得预先出现在文档里），meaning / tradeoffs 逐字出现为 warning。模板见 `assets/units-template/s01.md`。

## `teaching-guide.md`（1.0 / 1.1 旧课程）

旧的单文档讲义，校验器仍接受（`--guide`）。新课程不再生成。

来源定位应贴近结论。避免在正文中暴露 `criteria` 的完整参考答案；检查点只给问题，首次回答后再按需要提供 `hint`。

## 小节选择

一个小节围绕一个中心机制和少量直接相关概念。拆分或合并时以以下标准判断：

- 用户能否用一次解释说清楚它解决的问题、机制和结果；
- 它是否有独立的新问题或设计理由；
- 合并后是否造成需要同时记住太多平行细节；
- 拆分后是否只剩缺乏实际意义的术语定义。

## 质量检查

生成后执行：

```bash
# 大纲阶段
python3 scripts/validate_lesson.py path/to/lesson-plan.json \
  --outline path/to/outline.md --manifest path/to/sources.json --sources-root <材料根目录>
# unit 生成后
python3 scripts/validate_lesson.py path/to/lesson-plan.json \
  --outline path/to/outline.md --units-dir path/to/units --manifest path/to/sources.json --sources-root <材料根目录>
```

清单不是由脚本生成或路径不能一一对应时可省略 `--manifest`，但仍需人工检查引用是否可定位。`--sources-root` 让账本对照真实标题检查，长材料务必加。校验器检查结构和交叉引用，不证明教学解释本身正确。

## 导出机器参考图（开启知识库时）

校验通过后，把课程导出为分层的机器参考图：

```bash
python3 scripts/mrg_export.py path/to/lesson-plan.json --store whetstone/store [--manifest path/to/sources.json]
```

产出 `<store>/mrg/<lesson-id>.json`（公开层：`fact / mechanism` 节点与边、各节的问题 / 方案 / 机制骨架）与 `<store>/mrg/<lesson-id>.deep.json`（高层：`rationale / principle` 节点与边、各节的意义、代价、设计思想、检查标准）。**渲染讲义、生成概念笔记、回答学习者查询时只读公开文件；高层文件只在评估与出题时加载。** 已存在的导出不覆盖；修订 MRG 应产生新版本。未开启知识库时不需要此步。
