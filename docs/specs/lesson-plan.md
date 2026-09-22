# 课程文件：`lesson-plan.json`、`outline.md`、`units/`

一门课在 `whetstone/courses/<lesson-id>/` 下的文件，以及 `lesson-plan.json` 的字段与校验规则。规则的实现是 `plugin/skills/learn/scripts/validate_lesson.py`，模板在 `plugin/skills/learn/assets/`。骨架课与分支课（schema 1.3）的增量见 [domain-skeleton.md](domain-skeleton.md)。

## 1. 课程目录

```text
<lesson-id>/
├── lesson-plan.json            schema 1.2；骨架课与分支课 1.3
├── outline.md                  路线图、全部概念、覆盖表；大纲确认时呈现给学习者
├── units/<section-id>.md       每个非 deferred 的节一份，独立生成
├── sources.json                来源清单（source_manifest.py）；单个短材料可省略
├── learning-progress.json      进入教学时由 learning_state.py init 创建
├── prerequisite-plan.json      前置检查的计划（条件产物）
├── prerequisite-progress.json  前置作答与回程复测（条件产物）；缺口建成前置课，是同级的另一个课程目录
├── prerequisite-guide.md       旧课程的补充文档；1.4 起不再生成
├── zoom/<section-id>-guide.md  学习者选择细化时生成，一节最多一份
└── concepts/                   clarify 技能维护的按节概念解释（<节 id>.md）与 _inbox.md
```

旧课程的单文档 `teaching-guide.md`（schema 1.0 / 1.1）仍被校验器接受（`--guide`），新课程不再生成。

## 2. 顶层字段

| 字段 | 自版本 | 规则 |
|---|---|---|
| `schema_version` | 1.0 | `1.0` 到 `1.5` 之一；新课程写 `1.5`（1.4 的超集，1.5 字段都可选）；旧课程按原版本校验 |
| `lesson_id`、`title`、`learning_goal` | 1.0 | 非空字符串 |
| `source_manifest` | 1.0 | `sources.json` 的相对路径，或 `null`。清单的 `base_path` 记录材料根相对课程目录的位置（`../../..` 或 `../../../material/x`），校验器与评分器据此推出材料根，课程目录因此自包含 |
| `big_picture` | 1.0 | `{problem, outcome, system_map[]}`：材料总体解决的问题、学完应能做的事、从输入到结果的关键步骤 |
| `sections[]` | 1.0 | 非空，见 §3 |
| `final_challenge` | 1.0 | `{prompt, criteria[]}`，结课的迁移题 |
| `uncertainties[]` | 1.0 | 解析、证据或语义上的未决项，可为空 |
| `relations[]` | 1.1 | 见 §5 |
| `mode` | 1.2 | `full / fast` |
| `outline_confirmed_at` | 1.2 | 必须存在。`null` 表示大纲未确认，此时不得生成 `units/`；确认后写真实 ISO 时间，午夜占位报警告 |
| `deferred[]` | 1.2 | `[{type: section / concept, id, reason}]`，`id` 必须存在于本课 |
| `coverage[]` | 1.2 | 见 §7；为空时必须传 `--allow-empty-coverage` |
| `shape`、`parent_course`、`branch_candidates[]` | 1.3 | 见 domain-skeleton.md |
| `prerequisite_of`、`blocked_at`、`depth` | 1.4 | 前置课，三者同时出现：父课 `lesson_id`、父课被卡住的节 id、父课 depth + 1（主课为 0）；`shape` 必须是 `linear`，与 `parent_course` 互斥。校验器打印 `INFO: fact ratio a/b`（fact 层概念 / 全部概念），不设阈值 |
| `review_of[]` | 1.5 | 复习课：`shape: review` 时必填，列被复习的课程 id（不含本课）；其他形态不允许。复习课不允许探测题、分支候选、前置课字段；覆盖表可为空，材料就是被复习课的文件 |

## 3. `sections[]`

| 字段 | 规则 |
|---|---|
| `id`、`title` | `id` 唯一 |
| `depends_on[]` | 只能指向更早的节 |
| `problem`、`solution`、`mechanism` | 本节的问题、材料的方案、方案如何工作；渲染进 `units/` |
| `meaning` | 它的实际意义；rationale 层，只作出题素材，不渲染 |
| `tradeoffs[]` | 边界、代价、失败方式；rationale 层，不渲染。1.5 起条目可以是对象 `{text, contested, sides[]}`：`contested: true` 表示材料在此处不一致，`sides` 恰好两方，各带 `claim` 与 `source_refs[]`；不一致本身是事实，可以在讲义里说，主问题可以问“你信哪个、凭什么” |
| `new_problem` | 引向下一节的问题；除末节外非空，末节可为 `null` |
| `principle` | 1.1 可选。本节体现的可迁移设计思想；principle 层，不渲染 |
| `concepts[]` | 见 §4 |
| `source_refs[]` | 见 §8 |
| `checkpoint` | `{prompt, criteria[], hint}`，见 §6 |
| `probe` | 1.3，仅骨架课 |
| `parent_section` | 1.5 可选；复习课必填。`{lesson_id, section_id}`：本节重访或深化那一节。指向本课的节时不能是自身、不能成环；指向别的课时那门课必须在 `review_of` 里 |
| `review_kind` | 1.5，仅复习课，必填。`repeat`（重访原节，问题换情境）或 `deepen`（子节，`id` 用 `<原节>.1`）。`--units-dir` 加 `--reviewed <被复习课的 lesson-plan.json>` 时，节文档含被复习节 `solution / mechanism` 的整句原文报错 |

一门课超过 9 节报警告（骨架课除外）。

## 4. `concepts[]`

| 字段 | 自版本 | 规则 |
|---|---|---|
| `name`、`explanation` | 1.0 | 面向学习者的一句解释 |
| `id` | 1.1 | `<domain>.<concept>`，小写 ASCII，如 `cs.tee.enclave`；跨课稳定；同一 id 在多节出现时 `name` 必须一致 |
| `layer` | 1.1 | `fact / mechanism / rationale / principle` |
| `domain_path[]` | 1.1 | 1–4 级学科路径，如 `["计算机科学", "可信计算"]`；教学推断 |
| `aliases[]` | 1.1 | 可选，非空字符串 |
| `role` | 1.2 | `core / supporting / listed`，必填。`core` 进主问题，每节超过 4 个报警告，超出的降为 supporting 而不是删除；`supporting` 会讲，每节超过 6 个报警告；`listed` 只列名、一句事实层定义与定位，`explanation` 超过 200 字报警告 |
| `check` | 1.2 | 仅 `supporting`：`{prompt, criteria[], hint}`，学习者说"验收 X"时使用；缺失报警告 |
| `anchor` | 1.3 | 仅骨架课；给了 `--sources-root` 时校验器还会看落点处有没有讲解，见 [domain-skeleton.md](domain-skeleton.md) §4 |
| `contrast` | 1.5 | 可选。`{with, differs_in}`：最容易与本概念混淆的近邻（概念 id，不能是自身）和差在哪个变量；出题与反馈优先放在这里 |
| `cases[]` | 1.5 | 可选。恰好两个 `{summary, source_refs[]}`：表面不同、结构相同的案例，来自材料池或外部存档；讲义先摆案例再揭示机制 |
| `ontology` | 1.5 | 可选。`entity / process / constraint / relation`：本体类别，只在骨架课与前置课建议填；类别错置的回答要重新归类而不是反驳 |

## 5. `relations[]`

每条 `{id, from, to, type, layer, rationale?, source_refs[]}`。`from`、`to` 是本课出现的概念 id，不能相同；`type` 取 `is_a / part_of / depends_on / causes / enables / implements / contrasts_with / instance_of / prerequisite_for`；`prerequisite_for` 默认 `support: pedagogical_inference`。图示把 `type` 渲染成中文（是一种 / 属于 / 依赖 / 导致 / 促成 / 实现 / 对照 / 实例 / 前置），字段值本身不变。至少为每节的中心概念写一条它与前一节中心概念的边。校验器打印 `INFO: orphan concepts a/b`——没有出现在任何关系里的核心概念数，不设阈值；链重建对不到这些概念。`shape: review` 的课程与其他课程一样写 `relations[]`。

**跨课的边**：端点可以是本课没有的概念 id，条件是校验器带了 `--store` 且那个 id 在 `concepts/index.json` 的 `concepts` 里登记过；不带 `--store` 时仍然报错，离线校验不放宽。校验器打印 `INFO: relations n cross-lesson edges`。这样的边有三处不同：`lesson_section.py --section` 把它打进"跨课关系"，教学时在揭示方案与机制之前先问学习者（[protocol.md](protocol.md) 的 PREDICT），作答记 `--kind transfer --concept <他课 id>`；它不进结课链重建的参考边——学习者拿到的只有本课的概念名；`source_refs` 照常填本课材料里的定位，`rationale` 是判定这道题的依据。

## 5a. 节类型与系统结构图（1.6）

`sections[].kind` 缺省 `chain`（问题链节），此前的计划与模板不受影响；`structure` 是结构讲解节，`process` 是过程讲解节。三种节的字段差别：

| 字段 | `chain` | `structure` | `process` |
|---|---|---|---|
| `problem` / `mechanism` / `meaning` / `concepts` / `checkpoint` / `depends_on` / `source_refs` | 必填 | 必填 | 必填 |
| `solution` | 必填 | 不允许 | 不允许 |
| `new_problem` | 末节外必填 | 不允许 | 不允许 |
| `tradeoffs` | 列表，可空 | 必须为空 | 列表，可空 |
| `steps[]` | 不允许 | 不允许 | 必填，至少两条 |

`structure` 节的概念只能是 `supporting` 或 `listed`：它安放部件，不把核心概念送进检查点；出现在系统结构图上的概念必填 `ontology`。不在图上的概念只警告，不报错。`process` 节的 `steps[]` 每条 `{actor, target?, action, changes}`，`actor` 与 `target` 是本课概念 id（不是图上的部件时警告）；本节必须有一个 `ontology: process` 的核心概念——被追踪的那一种运行方式。本次不追踪的可选运行方式写成本节 `listed` 概念并填 `contrast.with` 指向它，课程范围外的进 `deferred[]`。

`big_picture.system_map` 仍可以是旧的步骤字符串数组；写成 `{components: [{id, parent?}], links: [{from, to, label}]}` 时，`id / parent / from / to` 是本课概念 id，或（校验器带 `--store` 时）知识库里登记过的他课概念 id。`parent` 表示包含，不许成环；`links` 是带一句文字说明的有向线，没有类型，不导出为参考图的边，也不进前置、假性掌握与链重建。课程含 `structure` 节时必须用这种形式。`sections[].position` 任何节类型可选，指出本节展开的是哪个部件。

骨架课里 `structure` 节不要 `probe`（它的答案在 `outline.md` 的系统图上），`process` 节照常要。图上的部件不计入 `INFO: orphan concepts`——它们靠 `links` 相连，不靠 `relations[]`；`structure` 节的概念不进结课链重建的名单，它是可随时回查的参考，不是凭记忆重建的内容。

## 6. 判定标准

`checkpoint.criteria[]`、`check.criteria[]`、`probe.criteria[]`、`final_challenge.criteria[]` 都是 `[{id, text, layer}]`（1.0 是字符串数组），`id` 在节内唯一，供 `criteria_met` 引用。所有 criteria 都不进任何面向学习者的文档。`hint` 是首次作答后按需给的渐进提示。

## 7. `coverage[]` 与 `deferred[]`

`coverage[]` 每行 `{path, heading, disposition, section_id?, reason?}`：

| `disposition` | 需要 | 含义 |
|---|---|---|
| `core / supporting / listed / appendix` | `section_id` 存在 | 这个标题的内容进了哪一节、什么角色 |
| `deferred / excluded` | `reason` | 略过（日后可补）/ 不讲 |
| `pool / reserve` | 骨架课；`pool` 另可用于任何课程的外部存档集（路径含 `external/` 段，`heading: "*"`） | 见 domain-skeleton.md；外部存档见 §8 |

传 `--sources-root <材料根>` 时，校验器读取来源文件（`.md / .adoc / .txt`）的一级、二级标题，每个标题都必须在表里有一行，否则报 `coverage is missing heading` 错误。这是"不静默遗漏"的确定性保证。

`deferred[]` 记录略过的节或概念。deferred 的节不生成 `units/<id>.md`（存在则警告）；`learning_state.py init` 把它标为 `deferred`，不计入完成。

## 8. `source_refs[]`

每条 `{path, locator, support, note}`。

- `locator` 以可机器核对的定位开头：文档用标题原文（`## Hello World`），代码用符号名（`create_report`），之后再加描述。`score_pack.py` 用第一段在原文里查找，得到 locator 命中率。
- `support`：`explicit / entailed / external / pedagogical_inference / unsupported`。`external` 的 `path` 指向 `<工作区>/external/<集名>_<日期>/` 下的存档文件（每集一份 `_index.md` 记 URL、发布方、访问时间、理由、定级），裸 URL 只在无法存档时允许且不进 `sources.json`；`unsupported` 不作稳定讲解的唯一依据。校验器打印 `INFO: external refs a/b`，不设阈值。
- 传 `--manifest sources.json` 时，`path` 必须在清单里（外部 URL 除外）。

## 9. `outline.md`

必含：学习目标、模式、材料范围；总体问题与系统地图（`diagram.py --system` 生成的 Mermaid 框图）；问题链，每节一行"编号、标题、问题 → 方案"，加 `diagram.py --chain` 生成的问题链图——1.5 课程校验器要求 `outline.md` 有 Mermaid 块且覆盖每个未略过的节；deferred 的节标"本次略过：理由"；学习情况——问题链表的状态列与文末 `<!-- whetstone:status -->` 块（进度、每节的状态、作答次数、最近判定、到达的层，有库时链重建比例，仍待复习的节）由 `outline_status.py --course <目录> [--store …]` 从进度文件生成，`learning_state.py` 与 `lrg_record.py` 每次写进度后自动刷新，结课总结写在块之后；全部概念按节、按角色列出（core 只列名，supporting 名 + 一句，listed 名 + 一句 + 定位，deferred 名 + 理由）；覆盖表摘要，`excluded` 附理由；使用说明（讲义在哪、怎么要求验收 supporting、怎么展开 listed、怎么补 deferred）。

校验：课程标题、模式、每个节标题、每个概念名都出现；`criteria`、`check.criteria`、`principle` 出现为错误；`meaning`、`tradeoffs` 逐字出现为警告。模板 `assets/outline-template.md`。

## 10. `units/<section-id>.md`

每个非 deferred 的节一份，独立生成，只带本节的来源定位读原文。必含：当前问题、（core 概念带 `cases` 时）两个案例并列并请学习者先写共同点、解决方案、工作机制、引出的新问题、本节概念（core / supporting / listed 三块可见；可选一张 `diagram.py --section <id>` 的关系图或按材料手写的机制框图，只画公开层；带 `contrast` 的一句点出近邻与差在哪个变量；supporting 各一段"在本节机制里的位置"；listed 只有名 + 一句 + 定位，不讲机制）、来源、"轮到你"检查点。不含 `meaning`、`tradeoffs`、`principle`、`criteria`。

校验：文件存在；含本节标题、`checkpoint.prompt` 原文、每个概念名；`criteria` 或 `principle` 泄漏为错误；`meaning`、`tradeoffs` 逐字出现为警告；supporting 概念旁的"验收 X"提醒为警告——只在 outline 的使用说明里写一次。模板 `assets/units-template/s01.md`。

## 11. 运行校验

```bash
# 大纲阶段
python3 scripts/validate_lesson.py lesson-plan.json --outline outline.md [--sources-root <材料根>]
# units 生成后
python3 scripts/validate_lesson.py lesson-plan.json --outline outline.md --units-dir units \
  --manifest sources.json            # 材料根从 sources.json 推出；没有清单时 --sources-root <材料根>
# 1.0 / 1.1 旧课程
python3 scripts/validate_lesson.py lesson-plan.json --guide teaching-guide.md
```

错误阻断，警告不阻断。校验器检查结构与交叉引用，不证明讲解本身正确。

## 12. 版本

| 版本 | 增加 |
|---|---|
| 1.0 | 线性问题链：每节 `problem / solution / mechanism / meaning / tradeoffs / new_problem / concepts / source_refs / checkpoint` |
| 1.1 | 概念 `id / layer / domain_path / aliases`；顶层 `relations[]`；`criteria` 改为对象数组；可选 `principle` |
| 1.2 | `mode`、`outline_confirmed_at`、概念 `role` 与 `check`、`deferred[]`、`coverage[]`；`outline.md` + `units/` 取代 `teaching-guide.md` |
| 1.3 | `shape`、`parent_course`、`pool / reserve`、`anchor`、`probe`、`branch_candidates[]` |
| 1.4 | 前置课：`prerequisite_of`、`blocked_at`、`depth`；任何课程可用外部存档集作 `pool` |
| 1.5 | 概念 `contrast / cases / ontology`；`tradeoffs[]` 条目可带 `contested` 与两方来源；节 `parent_section`；复习课 `shape: review`、`review_of[]`、节 `review_kind`。校验器打印 `INFO: variation a/b`（有易混对、有两个案例的核心概念数），不设阈值 |
| 1.6 | 节 `kind: chain / structure / process`（缺省 `chain`）、`steps[]`、`position`；`big_picture.system_map` 可写成 `{components, links}`。见 §5a |
