# 取向与骨架课（schema 1.3）

`orientation: material / domain` 是与 `mode` 正交的一个轴，在学习者档案里决定。`material`（默认）下课程范围由材料的结构决定，规则全部在 [lesson-plan.md](lesson-plan.md)；`domain` 下先学一门只讲基本原理的骨架课，材料作为证据池，学完由学习者选分支，每个分支变成一门普通课。本文只写 `domain` 取向增加的东西。实现：`validate_lesson.py` 的 `validate_v13`、`grounding`；协议 `learn/references/stages/skeleton.md`、`protocol/probe.md`、`protocol/finish.md`；示例 `learn/assets/skeleton-example/`。

## 1. 两个轴

| 轴 | 取值 | 决定什么 | 记在哪 |
|---|---|---|---|
| `mode` | `full / fast` | 一门课里每节的严格程度 | `lesson-plan.json` |
| `orientation` | `material / domain` | 课程范围由材料结构还是领域的原理结构决定 | `learner-profile.md` |

课程文件里不记 `orientation`，记 `shape`：`linear`（普通课，缺省）、`skeleton`（骨架课）、`branch`（分支课）。一门分支课的取向回到 material，所以用 `shape` 表达而不是 `orientation`。两个取向可以并存于同一个工作区：先 domain 骨架，后 material 分支。

档案阶段只问一句。学习者说"巩固 / 从头理解这个领域""材料太杂不知道从哪学"记 `domain`；说"学这份文档 / 这个仓库"记 `material`；拿不准默认 `material` 并标"默认值，可修改"。

## 2. 不设量化上限

不规定骨架概念数、探测题数、节数、骨架课数。规模由结构决定：骨架概念是领域的原理层概念——理解了它们，材料里的具体实现才可解释；先画它们之间的 `depends_on / enables / prerequisite_for` 依赖图，按拓扑分层切节，一节讲一个中心机制及其直接依赖；领域大就多切节，或在学习计划里拆成 `skeleton-1 → skeleton-2 …`。唯一保留的量化项是 `core ≤ 4 / 节` 的警告，它约束单次认知负荷，不约束领域规模。普通课 `> 9 节` 的警告对骨架课关闭。

## 3. schema 1.3 增量

| 字段 | 规则 |
|---|---|
| `shape` | `linear / skeleton / branch`，缺省 `linear` |
| `parent_course` | 仅 `branch` 必需，写骨架课的 `lesson_id`；只用于导航，不参与前置判定 |
| `coverage[]` | 骨架课按文件或目录记：`heading: "*"` 表示整个路径；`disposition` 新增 `pool`（证据池，骨架课可引用）与 `reserve`（留给分支课，`reason` 可选）；`*` 只允许配 `pool / reserve / excluded`；`--sources-root` 对 `*` 路径跳过逐标题检查。C 级材料只能 `excluded`。分支课与普通课仍逐标题 |
| `concepts[].anchor` | 骨架课的 `core / supporting` 必需：`{path, locator}`（`path` 必须在某个 `pool` 行之下，`locator` 规则同 `source_refs`）、`"external"`（材料里没有，原理必需）或 `"no-anchor"`（没找到落点，警告，学习者决定留不留） |
| `sections[].probe` | 骨架课每节必需：`{prompt, criteria[{id,text,layer}], hint?}`，原理层、无提示、不依赖材料细节。`probe.criteria` 不进任何文档；`probe.prompt` 出现在 `units/` 里为错误——探测题在教学前无提示作答 |
| `branch_candidates[]` | 骨架课必需，至少一条：`{id, title, concept_ids[], materials[], work_relevance?, status}`。`concept_ids` 指向本课概念；`materials` 必须在 `pool` 或 `reserve` 之下，no-anchor 候选可为空；`status` 为 `candidate / chosen / declined`；`outline.md` 必须列出每个候选的 `title` |

骨架课的 `source_refs` 与 `anchor` 只指向 `pool` 里的 A 级材料；`final_challenge` 与迁移题只用学习者的实际材料出题。

**落点比例**：校验器打印 `INFO: grounding a/b`，a 是有 A 级落点的 core + supporting 概念数，b 是全部 core + supporting 概念数。只展示，不设阈值，由学习者判断骨架是否漂得太远。`outline.md` 把它原样写进"落点比例"。

## 4. 建骨架课

阶段 2 材料评估在 domain 取向下不做逐标题账本，改为给每份材料一个去处（`pool / reserve / excluded`），B 级进 `pool` 前问学习者。阶段 3 的计划分两段：一门或几门骨架课；一张分支候选草表，现在不确认、不排序、不出大纲。

阶段 4 按 `stages/skeleton.md`：

1. `coverage[]` 按文件写，每份材料恰好一个去处；
2. 先画原理依赖图再切节；
3. 每个 core / supporting 概念填 `anchor`；
4. 每节写 `probe`，与 `checkpoint` 是两道不同的题；
5. 填 `branch_candidates[]`：骨架概念 → 材料里的文件或模块 → 对应实际工作的哪部分；每节至少落到一个候选，多节可共用；
6. 写 `lesson-plan.json`（`schema_version: "1.3"`, `shape: "skeleton"`, `outline_confirmed_at: null`）与 `outline.md`，校验，把落点比例写进 outline。

呈现大纲时额外说明三件事：骨架讲通用原理，与教科书重合是正常的，相关性看落点比例与分支候选两张表；`no-anchor` 的概念列出来，留不留由学习者定；确认后先做一轮探测。确认问题比普通课多一句"no-anchor 的概念留不留？"

## 5. 前置地图与探测轮

在大纲确认、`units/` 生成、`learning_state.py init` 之后，教学之前依次运行。先做前置地图：从 `units/` 正文取出用来解释机制、而本课 `concepts[]` 没有定义的概念（这一步总是做，空集则跳过），按 `prerequisite_check` 决定诊断深度——`always` 直接诊断，`skip` 只列清单，`auto` 列清单并问一句；要诊断时按前置检查协议的阶段一、二处理，非 `ready` 的簇按依赖类型分流，建了前置课时状态是 `BLOCKED`，回程后再探测。探测轮本身量的是原理层的地板，与前置地图不重复出题。

1. 一句话说明规则：每节一道无提示题，考原理不考材料细节；答对可以跳过该节，答不对不扣分。
2. 按节顺序一次一题，只给 `probe.prompt`，不给提示和材料。
3. 对照 `probe.criteria` 判 `mastered / partial / misconception`，记 `depth_reached`，一句话反馈，不展开讲解。
4. 开启知识库时 `lrg_record.py append --kind probe`（即时证据）。
5. `mastered` 的节列为候选。全部探测结束后一次性列出，问学习者"跳过还是照学"；只有学习者选跳过的节才 `learning_state.py defer --reason "原理探测通过，学习者选择跳过"`，同时写进 `deferred[]` 并更新 outline 的状态列。学习者也可以说"全部照学"或"跳过探测"。

探测阶段不补课、不桥接；探测结果不作能力标签；探测题不代替节的主问题——跳过的节之后仍可通过 resume 的变式题补证据。

## 6. 分支决策

骨架课结课总结之后：

1. 呈现 `branch_candidates[]`：对应原理、材料路径、`work_relevance`，以及本课中相关概念的验收结果；
2. 问学习者要深入哪些分支、什么顺序，也可以"不深入，结束"；
3. 写回 `status`：选中的 `chosen`，其余 `candidate` 或学习者明确不要的 `declined`；
4. 每个选中的分支追加到 `learning-plan.md` 为一门普通课：`shape: branch`、`parent_course` 为本课 `lesson_id`、材料为候选的路径，取向回到 material，逐标题覆盖表照常；给出它的 `learn` 调用语句。分支课的大纲在它自己开始时才做。

开启知识库时，分支课的前置判断按概念 id 命中骨架课已记录的证据，这是概念索引本来的工作方式；`parent_course` 不参与。

## 7. 与知识库的关系

`mrg_export.py` 导出骨架课时带 `shape`、`parent_course`、`branch_candidates`、`grounding`；节点带 `anchor: anchored / external / no-anchor`，字典形式的 `anchor` 作为概念级 `source_refs` 一并导出（`note: skeleton anchor`），`external` 锚导出为 `support: external`；每节带 `probe_prompt`。LRG 的 `kind: probe` 记为即时证据。
