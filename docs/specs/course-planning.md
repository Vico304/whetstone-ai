# 设计定稿 C：课程规划——大纲、按 unit 生成、模式、概念角色

> 文档性质：规范性设计定稿（schema 1.2）。回答"复杂材料如何规划课程、如何避免静默遗漏"。
> 状态：已定稿（2026-09-06），实现见 roadmap P0.5。
> 上位文档：[consensus.md](../consensus.md)；相关：[knowledge-store.md](knowledge-store.md)、[protocol-architecture.md](protocol-architecture.md)、[../learning-layers.md](../learning-layers.md)。
> 触发：使用者用 0.2.0 学 RISC-V CoVE 规范的反馈——"核心概念抓取准确，但长材料里 page fault、时钟中断等关键细节没涉及"。根因不是抽取，是规划：一次性生成、不可协商、没有覆盖账本。

---

## 1. 决策

| # | 决策 |
|---|---|
| C1 | **大纲是 build 的第一阶段产物，也是一个必经的停顿点。** 两种模式都生成大纲、都呈现给学习者并等一句确认（默认值可直接接受）。确认后才生成 unit 文档 |
| C2 | **每个 unit 一份文档，独立生成、独立校验**，`units/<section-id>.md`。build 阶段全部生成完再开课（学习中途等待损害体验）；宿主支持时并行生成。`teaching-guide.md` 由 `outline.md` 取代 |
| C3 | **两种模式** `full / fast`，在大纲确认时选定。快速模式 = 缩小范围 + 容忍模糊 + 整体框架验收；**揭示顺序不变**（预测 → 揭示 → 重建），否则退化为摘要器 |
| C4 | **概念分角色** `core / supporting / listed`，外加 `deferred`。4±1 上限只约束 `core`；`listed` 无上限但只给名字、一句事实层定义与定位，不讲机制 |
| C5 | **supporting 概念有自己的验收问题**（`supporting_checkpoints`），学习者选择深入时作答；不阻塞主线，记入 LRG |
| C6 | **覆盖账本**：材料的每个标题与抽取出的每个候选概念都必须有去处；校验器逐条检查。遗漏从静默变为显式 |
| C7 | 快速模式的证据在学习者状态里打折：LRG 事件带 `rigor`；只有快速证据的概念跨课复用时按 `stale` 处理 |

## 2. 产物

```text
<course>/
├── outline.md                # 取代 teaching-guide.md：目标与模式、问题链、每 unit 一句问题/方案、
│                             # 全部概念（按角色）、覆盖账本摘要、deferred 清单、预计深度
├── lesson-plan.json          # 1.2
├── units/
│   ├── s01.md                # 每 unit 一份：问题、方案、机制、supporting 概念段、listed 概念表、来源、检查点
│   └── ...
├── coverage.json             # 覆盖账本（也可内嵌 lesson-plan.coverage）
├── sources.json / prerequisite-* / learning-progress.json / zoom/ / concepts/   # 不变
```

## 3. 流程

```text
1. 范围与来源（不变；长材料时分块抽取候选概念 + 定位，见 spec B S2 / aux 阶段）
2. 生成大纲：lesson-plan.json（sections 只填 problem / solution / concepts+role / source_refs；
   status = "outline"）+ coverage + outline.md → validate_lesson.py --outline
3. 呈现大纲，问一句：模式（full / fast）+ 想跳过或加深的 unit / 概念
   → confirm_outline.py --mode … [--defer …] 写入 mode、outline_confirmed_at、deferred
4. 前置阶段（不变；开启知识库时先查注册表）
5. 逐 unit 生成 units/<id>.md 并补全 lesson-plan 该节的 mechanism / meaning / tradeoffs /
   principle / checkpoint / supporting_checkpoints；status = "generated"；每份单独校验；
   宿主支持子代理时并行
6. 全部生成后 mrg_export（角色随节点导出）→ 开课
```

第 3 步是唯一新增的交互；一次往返。SKILL.md 的"低输入自动补全"原则对大纲确认让步。

## 4. 概念角色

| 角色 | unit 文档里 | 验收 | 计入上限 | 之后 |
|---|---|---|---|---|
| `core` | 完整讲：解决什么问题、机制、来源 | 主问题 `checkpoint`（criteria 只能引用 core） | core ≤ 4（warning） | — |
| `supporting` | 讲，作为 core 的配角：一段说明它在本节机制里的位置 | `supporting_checkpoints[]`：每个（或每组）supporting 概念一道题，学习者选择深入时作答；追问可涉及 | supporting ≤ 6（warning） | — |
| `listed` | 只有名字 + 一句事实层定义 + 原文定位；**不讲机制** | 不考 | 无上限 | 自动成为 zoom / clarify 候选 |
| `deferred` | 不出现在 unit 文档；大纲里标"本次略过 + 理由" | 不考 | — | 账本 + 学习者状态 `unknown`，以后可补 |

不变量：**学习者不可能对材料涉及的概念完全不知情**——三道保证：(a) 覆盖账本映射每个标题；(b) 每个候选概念必须分配角色；(c) unit 文档可见 core / supporting / listed 全部名字。边界：`listed` 不给机制，否则成为首次重建前泄露参考的后门。

## 5. 模式

| 环节 | `full` | `fast` |
|---|---|---|
| 范围 | 全部 unit；core 全进检查点 | 只保留主线 core unit；其余 `deferred` |
| 大纲确认 | 必经 | 必经 |
| 揭示顺序 | 预测 → 揭示 → 重建 | **相同** |
| 评估 | `partial` → 针对性追问，最多两层 | `partial` 且方向大致对 → 直接给修正、记录、进下一节；仅会断掉后续因果链的误解 `retry` |
| supporting 验收 | 学习者选择时进行 | 同 |
| 结课 | 整体重述 + 迁移题，按 criteria 判 | 整体重述必做，标准是"能把问题链串起来、关键取舍说出方向"，不求每处准确；迁移题可选 |
| 证据 | `rigor = full` | `rigor = fast`：学习者状态里只有 fast 证据的概念，`freshness` 最高为 `stale`；跨课前置按 `variant_then_diagnose` |

## 6. 覆盖账本

`coverage[]` 每项：

```json
{"source": "src/sbi_cove.adoc", "heading": "TVM exit handling", "target": {"section_id": "s05", "role": "supporting"}}
{"source": "src/sbi_cove.adoc", "heading": "Error codes", "target": "deferred", "reason": "逐条错误码不支撑主线"}
{"source": "src/appendix_b.adoc", "heading": "CDDL", "target": "excluded", "reason": "证据格式属相关规范"}
```

校验：给 `--sources-root` 时，来源文件（`.md / .adoc / .txt`）的每个一至二级标题都必须出现在账本；每个 `deferred / excluded` 必须有 `reason`；`target.section_id` 必须存在；`target.role` 取自角色集。候选概念（分块抽取产出）用 `candidates[]` 记录，每个必须映射到某节某角色或 deferred。

## 7. supporting 验收

`sections[].supporting_checkpoints[]`：`{id, concept_ids[], prompt, criteria[{id,text,layer}], hint}`。规则：

- 由学习者在 MAIN 阶段选择"深入本节的 X"时触发（取代原 DEEPEN 的抽象询问，候选就是本节 supporting 概念）；
- 作答走正常评估与反馈；verdict 记入 LRG（`scope = supporting`），**不改变本节状态与当前位置**；
- `zoom/<id>-guide.md` 保留为可选的进一步细化文档，不再是验收的前提；
- 快速模式下同样可用。

## 8. schema 1.2 变更

| 字段 | 说明 |
|---|---|
| 顶层 `mode` | `full \| fast`；大纲阶段可缺省，确认后必填 |
| 顶层 `outline_confirmed_at` | ISO 时间；缺省表示尚未确认 |
| 顶层 `deferred[]` | `{kind: section \| concept, id, reason}` |
| 顶层 `coverage[]`、`candidates[]` | 见 §6 |
| `sections[].status` | `outline \| generated`；outline 时只要求 `id / title / depends_on / problem / solution / concepts / source_refs`；generated 时要求 1.1 的全部字段 |
| `sections[].concepts[].role` | `core \| supporting \| listed`，必填 |
| `sections[].supporting_checkpoints[]` | 见 §7 |
| `checkpoint.criteria[]` | 不变；新增校验：criteria 涉及的概念必须是 core（通过可选 `concept_ids`） |

产物校验：`validate_lesson.py plan.json --outline outline.md --units-dir units/ [--sources-root …]`。outline 检查：课程标题、所有小节标题、所有非 deferred 概念名出现；不泄漏 criteria / principle。unit 检查：本节标题、检查点、本节 core+supporting+listed 名字出现；不泄漏。1.0 / 1.1 单文档包继续用 `--guide`。

## 9. 与其他部分的关系

- 知识库：LRG 事件新增 `rigor`、`scope`；`learner_state_build` 计算 `rigor_max` 并对只有 fast 证据的概念降级；`index_match prerequisites` 相应处理；`comparator` 的 `missing` 只统计 core + supporting。
- 协议：新增 `protocol/outline.md`；`main.md` 的细化询问改为列出本节 supporting 概念；`assess.md / feedback.md / finish.md` 各加快速模式分支。
- eval：`score_pack` 新增角色分布、账本完整率、deferred 数、unit 文档数。
- 分块候选抽取（spec B S2 / aux 模型）是 §4 不变量 (b) 的前提；本 spec 不依赖它落地，但没有它时 (b) 的强度取决于模型是否读全材料。

## 10. 不做

- 不做自动判定模式；不做无确认的大纲；
- 不在快速模式跳过预测与重建；
- 不让 `listed` 概念带机制说明；
- 不把 supporting 验收设为进入下一节的门槛。
