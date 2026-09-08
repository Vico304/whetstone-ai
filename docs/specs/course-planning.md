# 设计定稿 C：课程规划——大纲、按 unit 生成、模式、概念角色

> 文档性质：规范性设计定稿（schema 1.2）。回答"复杂材料如何规划课程、如何避免静默遗漏"。
> 状态：已定稿（2026-09-06）；2026-09-07 按实现（提交 `b009f22`，schema 1.2）校正字段名与流程，并加入规划管线分层（§11）。实现与本文档不一致处以脚本为准并回改本文档。2026-09-08 起由 [domain-skeleton.md](domain-skeleton.md)（规格 D，schema 1.3）增补取向轴：本文的数字（unit 数、概念数）一律视为建议值，只有 `core ≤ 4` 是校验器警告。
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
| C5 | **supporting 概念各自带一道可选验收题**（`concepts[].check`），学习者说"验收 X"时作答；不阻塞主线，记入 LRG（`kind: supporting`） |
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
├── sources.json / prerequisite-* / learning-progress.json / zoom/ / concepts/   # 不变
（覆盖账本内嵌为 lesson-plan.json 的 coverage[]；工作区根另有跨课的 learner-profile.md 与 learning-plan.md，见 §11）
```

## 3. 流程

```text
0. 缺什么补什么（learn 启动时）：无 learner-profile.md → 阶段 1；材料是目录/太大 → 阶段 2、3；
   本课无确认大纲 → 阶段 4；有进度 → resume（见 §11 与 learn/references/stages/_index.md）
1. 范围与来源（不变；长材料时分块抽取候选概念 + 定位，见 spec B S2 / aux 阶段）
2. 生成大纲：lesson-plan.json（1.2：sections 含 problem / solution / mechanism / concepts+role /
   source_refs / checkpoint；顶层 mode、outline_confirmed_at: null、coverage[]、deferred[]）
   + outline.md → validate_lesson.py --outline [--sources-root]
3. 呈现大纲，问一句：模式（full / fast）+ 想略过或加深的 unit / 想升 core 的概念
   → 模型写回 mode、deferred[]、outline_confirmed_at，重新校验
4. 前置阶段（不变；开启知识库时 index_match.py prerequisites 先查注册表）
5. 逐 unit 生成 units/<id>.md（每份一次独立生成；宿主支持子代理时并行）
   → validate_lesson.py --units-dir 逐份校验
6. 全部生成后 mrg_export（角色随节点导出）→ learning_state.py init（deferred 节标 deferred）→ 开课
```

第 3 步是唯一新增的交互；一次往返。SKILL.md 的"低输入自动补全"原则对大纲确认让步。

## 4. 概念角色

| 角色 | unit 文档里 | 验收 | 计入上限 | 之后 |
|---|---|---|---|---|
| `core` | 完整讲：解决什么问题、机制、来源 | 主问题 `checkpoint` | core ≤ 4（warning） | — |
| `supporting` | 讲，作为 core 的配角：一段说明它在本节机制里的位置 | `concepts[].check`：每个 supporting 概念一道可选验收题，学习者说"验收 X"时作答；追问可涉及 | supporting ≤ 6（warning） | — |
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
| supporting 验收 | 学习者要求时进行 | 同 |
| 结课 | 整体重述 + 迁移题，按 criteria 判 | 整体重述必做，标准是"能把问题链串起来、关键取舍说出方向"，不求每处准确；迁移题可选 |
| 证据 | `rigor = full` | `rigor = fast`：`learner-state.json` 记 `rigor_max`；`index_match.py prerequisites` 把只有 fast 证据的 `fresh` 概念降为 `stale`（`variant_then_diagnose`） |

## 6. 覆盖账本

`coverage[]` 每项（内嵌于 `lesson-plan.json`）：

```json
{"path": "src/sbi_cove.adoc", "heading": "TVM exit handling", "disposition": "supporting", "section_id": "s05"}
{"path": "src/sbi_cove.adoc", "heading": "Error codes", "disposition": "deferred", "reason": "逐条错误码不支撑主线"}
{"path": "src/appendix_b.adoc", "heading": "CDDL", "disposition": "excluded", "reason": "证据格式属相关规范"}
```

`disposition ∈ core | supporting | listed | appendix | deferred | excluded`。校验：前四种必须有存在的 `section_id`，后两种必须有 `reason`；给 `--sources-root` 时，来源文件（`.md / .adoc / .txt`）的每个一至二级标题都必须出现在账本（`validate_coverage_against_sources`）。候选概念的完整性由分块抽取保证（spec B），本版本不单独记录 `candidates[]`。

## 7. supporting 验收

`sections[].concepts[].check`（仅 `role: supporting`）：`{prompt, criteria[{id,text,layer}], hint}`。规则：

- 由学习者说"验收 X"触发（`protocol/main.md`）；DEEPEN 的细化候选改为本节 `listed` 概念；
- 作答走正常评估与反馈（追问最多一层）；记录 `lrg_record.py append --kind supporting --concept <id>`，**不加 `--progress`，不改变本节状态与当前位置**；
- `check.criteria` 与主 criteria 一样不进任何面向学习者的文档（校验器检查 outline 与 units）；
- `zoom/<id>-guide.md` 保留为可选的进一步细化文档；
- 快速模式下同样可用。

## 8. schema 1.2 变更

| 字段 | 说明 |
|---|---|
| 顶层 `mode` | `full \| fast`，必填 |
| 顶层 `outline_confirmed_at` | 必须存在；`null` 表示尚未确认，此时不得生成 units |
| 顶层 `deferred[]` | `{type: section \| concept, id, reason}` |
| 顶层 `coverage[]` | 见 §6（可为空仅当 `--allow-empty-coverage`） |
| `sections[].concepts[].role` | `core \| supporting \| listed`，必填；`listed` 的 `explanation` > 200 字 warning |
| `sections[].concepts[].check` | 见 §7，仅 supporting 允许 |
| `checkpoint.criteria[]` | 1.1 对象数组不变 |

产物校验：`validate_lesson.py plan.json --outline outline.md --units-dir units/ [--sources-root …]`。outline 检查：课程标题、模式、所有小节标题、所有概念名出现；不泄漏 criteria / `check.criteria` / principle / meaning / tradeoffs。unit 检查（非 deferred 节）：文件存在、本节标题、检查点、本节全部概念名出现；criteria / principle 泄漏为错误，meaning / tradeoffs 逐字出现为 warning。1.0 / 1.1 单文档包继续用 `--guide`。

## 9. 与其他部分的关系

- 知识库：LRG 事件新增 `rigor` 与 `kind: supporting`（带 `target_concept_ids`）；`learner_state_build` 计算 `rigor_max`；`index_match prerequisites` 对只有 fast 证据的概念降级；`comparator` 的 `missing` 只统计 core，supporting 未提及进 `unmentioned_supporting`，listed 永不算缺。
- 协议：大纲确认在 `learn/references/stages/outline.md`；`main.md` 增加 supporting 验收入口，DEEPEN 候选取本节 listed 概念；`assess.md / feedback.md / finish.md` 各加快速模式分支。
- eval：`score_pack` 新增 `mode`、角色分布、账本各去向计数、deferred 数、`units_present`。
- 分块候选抽取（spec B S2 / aux 模型）是 §4 不变量 (b) 的前提；本 spec 不依赖它落地，但没有它时 (b) 的强度取决于模型是否读全材料。

## 10. 不做

- 不做自动判定模式；不做无确认的大纲；
- 不在快速模式跳过预测与重建；
- 不让 `listed` 概念带机制说明；
- 不把 supporting 验收设为进入下一节的门槛。

## 11. 规划管线分层（2026-09-07 增补）

用户提议并批准：规划分三层、三个寿命，`learn` 是总入口、缺什么补什么，`guide` 与 `outline` 是可重入的阶段入口，协议只在 `plugin/skills/learn/references/stages/` 维护一份。

| 阶段 | 产物（位置） | 寿命 | 入口 |
|---|---|---|---|
| 1 目标与背景 | `learner-profile.md`（工作区根） | 跨课，慢变 | `guide`（每次先问"怎么用 / 规划"）、`learn` |
| 2 材料评估 | `materials-survey.md/json`（`survey_materials.py`，不读正文；A 一手 / B 自著已核实 / C 生成中间物 / D 噪声） | 一次规划 | `guide`、`learn` |
| 3 学习计划 | `learning-plan.md`（课程序列，**逐门确认**） | 一组课 | `guide`、`learn` |
| 4 课程大纲 | `courses/<id>/outline.md` + `lesson-plan.json` | 一门课 | `outline`、`learn` |
| 5 build 与教学 | `units/`、进度、知识库 | 一门课 | `learn` |

规则：AI 生成的中间文档（会话总结、交接、汇报）最多作导航，永不列为课程来源；目的（学上游 / 巩固自己做过的 / 接手别人的）必须问，它决定哪一级材料进课程；参与度上限——熟手一轮就看到第一道题，新手最多三轮，每阶段只问一个问题；大纲在该课开始时才做，不预先做所有课的大纲。原 `brief` 技能并入 `guide`。

