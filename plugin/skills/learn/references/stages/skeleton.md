# 阶段 4（骨架课）：证据池 → 原理依赖图 → 大纲 → 确认

档案 `orientation=domain`、计划里这门课是骨架课时，用本文件代替 [outline.md](outline.md) 的"生成大纲之前"部分；**呈现与确认**、写回规则与 outline.md 相同。规格：`docs/specs/domain-skeleton.md`。

## 生成大纲之前

1. 读 `learner-profile.md`（目标、深度默认值、知识库）与 `learning-plan.md` 里骨架课的条目（证据池、保留项、分支候选草表）；
2. `coverage[]` 按**文件/目录**写：`{path, heading: "*", disposition: pool | reserve | excluded}`；每份材料恰好一个去处，C 级只能 `excluded`；
3. **先画原理依赖图，再切 unit**（图里包括从前一门课沿用的概念：对每个这样的概念至少写一条 `relations` 边，端点用知识库里的 id）：列出这个领域的原理层概念（理解了它们，材料里的具体实现才可解释），标出概念之间的 `depends_on / enables / prerequisite_for`；按拓扑分层，一个 unit 讲一个中心机制及其直接依赖。**不设概念数、unit 数上限**——领域大就多切 unit，或在计划里拆成多门骨架课；唯一的量化提醒仍是 `core ≤ 4 / unit`（警告，降级不删除）；
4. 每个 `core / supporting` 概念填 `anchor`：在证据池里找一处 A 级定位 `{path, locator}`（定位规则同 lesson-contract：标题原文或符号名开头）；材料里确实没有但原理必需 → `"external"`；没找到落点 → `"no-anchor"`（校验器警告，留给学习者决定）。**骨架课的 `source_refs` 与 `anchor` 只允许指向 `pool` 里的 A 级材料**；
5. 每个 unit 写 `probe`：一道**无提示、原理层、不依赖材料细节**的问题，criteria 与 checkpoint 一样对学习者隐藏；**`probe` 与 `checkpoint` 是两道不同的题**：probe 在教学前不看材料作答，checkpoint 在读完 unit 后作答——unit 文档的"轮到你"只放 `checkpoint.prompt`，探测题不写进任何文档（校验器报错）；
6. 填 `branch_candidates[]`：骨架概念 → 材料里的文件/模块（`pool` 或 `reserve` 之下）→ `work_relevance`（对应实际工作的哪一部分，没有就省略）；每个 unit 至少落到一个候选，多个 unit 可共用；没有落点的概念在表里标 no-anchor；`status` 一律 `candidate`；
7. `final_challenge` 与迁移题**只用学习者的实际材料**出题（这是第三道相关性锚）；
8. 写 `lesson-plan.json`（`schema_version: "1.6"`, `shape: "skeleton"`, `outline_confirmed_at: null`）与 `outline.md`（模板：`assets/skeleton-example/`），运行
   `validate_lesson.py <plan> --outline outline.md --sources-root <材料根> [--store <工作区>/store]`；把它打印的 `INFO: grounding …` 原样写进 outline 的"落点比例"，把 `WARNING: thin anchor …` 与 `INFO: … thin anchors` 各行写在它下方。
9. 大纲确认并生成 `units/` 之后，按 [../protocol/probe.md](../protocol/probe.md) 先做前置地图（单元正文用到而本课未定义的概念），再做探测轮。

## 呈现时额外说明

在 outline.md 的常规内容之外，明确告诉学习者三件事：

- 骨架课讲的是通用原理，与教科书重合是正常的；相关性看"落点比例"和"分支候选"两张表——**没有阈值**，漂不漂由你判断；
- `no-anchor` 的概念列出来了：保留（通识）还是删掉由你定；
- 落点薄的概念也列出来了（落点在数据或代码文件里，或定位处没有成段的讲解）：补材料还是照建由你定；
- 确认后先看单元正文里有没有你不熟的词（不熟的先补），再做一轮原理探测（[../protocol/probe.md](../protocol/probe.md)），答对的 unit 可以跳过。

确认问题与 [outline.md](outline.md) 相同（模式 + 略过/加深/升级），多加一句："no-anchor 的概念留不留？"
