# 规格 D：学习取向与骨架课（schema 1.3）

> 状态：定稿（2026-09-08）。补充 [course-planning.md](course-planning.md)（规格 C）；C 的一切规则仍然有效，本规格只增加一个正交维度。
> 起因：参考材料"太多太杂"时，按标题的覆盖账本要求对每一份材料都作出去处判断，规划成本随材料量线性增长，而学习者真正想要的常常是"先把这个领域的基本原理巩固一遍，再决定深入哪一块"。

## 1. 取向（orientation）是一个正交轴，不是第三种模式

| 轴 | 取值 | 决定什么 |
|---|---|---|
| 模式 `mode` | `full / fast` | 一门课里每个 unit 的严格程度（规格 C） |
| 取向 `orientation` | `material / domain` | 课程范围由什么决定：**材料**的结构，还是**领域**的原理结构 |

- `material`（默认）：学习对象就是这批材料。覆盖账本按标题逐条记录，材料的每个部分都要有去处。这是规格 C 的全部行为。
- `domain`：学习对象是材料所属的领域。先学一门（或多门）**骨架课**，只讲基本原理；学完后由学习者决定深入哪些分支，每个分支再变成一门 `material` 取向的普通课。材料在骨架阶段是**证据池**而不是覆盖对象。

取向在阶段 1（档案）确定，写入 `learner-profile.md`；两个取向可以并存于同一个工作区（先 domain 骨架，后 material 分支）。两个取向下 `mode` 仍各自独立选择。

判定建议（阶段 1 只问一句）：学习者说"巩固/从头理解这个领域""材料太杂不知道从哪学"→ `domain`；说"学这份文档/这个仓库"→ `material`。拿不准时默认 `material`，并在档案里标 `（默认值，可修改）`。

## 2. 不设量化上限

本规格**不规定**骨架概念数、探测题数、unit 数、骨架课数量。理由：这些数字约束的是领域规模，而领域规模不是我们能决定的。规模由结构决定：

- 骨架概念 = 领域的**原理层**概念（理解了它们，材料中的具体实现才可解释），及其依赖关系；
- unit 按依赖图**拓扑分层**切分：一个 unit 讲一个中心机制及其直接依赖；
- 领域大 → unit 多，或拆成多门骨架课（`skeleton-1 基础 → skeleton-2 …`），在学习计划里按依赖排序。这是普通的课程切分，不是新概念。

唯一保留的量化项是规格 C 已有的 **`core ≤ 4 / unit` 警告**：它约束的是单次认知负荷，不是领域规模——领域大就多切 unit，不把 unit 撑大。所有其它数字（如 triage 里的"≤ 30 KB / 4–8 unit"）都是**建议值**，只影响切分建议，不进校验器。

## 3. 骨架允许教科书化，但两道锚保证相关性

骨架课讲的是通用原理，内容与教科书重合是正常的、被接受的。相关性不靠限制内容保证，靠两道锚：

1. **概念锚（grounding）**：骨架课里每个 `core / supporting` 概念必须有 `anchor`——证据池中一处 A 级定位 `{path, locator}`，或显式的 `"external"`（材料里没有，但原理必需）、`"no-anchor"`（还没找到落点）。校验器：缺 `anchor` 为错误；`no-anchor` 为警告。`outline.md` 显示 **grounding 比例** = 有 A 级落点的概念 / 全部 core+supporting 概念，**不设阈值**，由学习者判断骨架是否漂得太远。
2. **分支候选表（branch_candidates）**：骨架概念 → 学习者材料里对应的文件/模块/子系统，附"对应实际工作的哪一部分"（如果有）。每个骨架 unit 至少对应一个候选（可以多个 unit 共用一个候选）。没有落点的概念在表里标 `no-anchor`，学习者决定保留（通识）还是删除。

第三道软锚：迁移题（`--kind transfer`）只用学习者的实际材料出题。

## 4. 证据池取代逐标题账本（仅骨架课）

骨架课的 `coverage[]` 按**文件或目录**记录，不按标题：

| disposition | 含义 | 需要 |
|---|---|---|
| `pool` | 进入证据池，骨架课按需引用其中的定位 | — |
| `reserve` | 留给分支课，骨架课不引用 | `reason` 可选 |
| `excluded` | 不用 | `reason` |

`heading` 写 `"*"` 表示整个文件/目录；校验器对 `heading: "*"` 的路径跳过逐标题检查。C 级材料仍然只能 `excluded` 或作为出题背景（规格 C §2 的纪律不变）；`anchor.path` 必须落在某个 `pool` 行的路径之下。

普通课（`shape: linear` 与 `branch`）的覆盖账本规则不变。

## 5. 原理探测取代前置诊断（仅骨架课）

骨架课不跑 `prerequisite/` 协议；取而代之每个 unit 带一道**原理探测** `sections[].probe {prompt, criteria[], hint?}`（无提示、原理层、不依赖材料细节）。校验器：骨架课每个 section 必须有 `probe`；`probe.criteria` 与 checkpoint 的 criteria 一样不得进入任何面向学习者的文档。

探测在大纲确认、units 生成之后、正式教学之前作为一轮进行（`protocol/probe.md`）：逐题问，学习者作答后按 criteria 判定，`lrg_record.py --kind probe` 记录。通过的 unit 标 `skip_candidate`，**由学习者确认**后写入 `deferred[]`（`reason: "原理探测通过，学习者选择跳过"`）；学习者也可以要求全部照学。探测不通过不做任何补救，直接按顺序学骨架。

## 6. 分支决策在骨架课结束时

`finish.md` 在骨架课末尾多一步：呈现分支候选表（含每个候选对应的骨架概念、材料路径、与实际工作的关系），学习者选择要深入的分支，顺序自定。每个被选中的分支：

- `branch_candidates[].status` 改为 `chosen`，其余 `candidate` / `declined`；
- 在 `learning-plan.md` 追加一门课（`shape: branch`，`parent_course` 指向骨架课 id，材料 = 候选的路径），走普通的阶段 4 → 5；
- 分支课的 `lesson-plan.json` 可以用 `parent_course` 让 `index_match.py prerequisites` 把骨架概念视作已有证据（骨架课记录在知识库里时）。

学习者也可以选择"不深入，结束"。

## 7. schema 1.3 增量（对 1.2 的超集）

```text
root.shape                 linear | skeleton | branch   （缺省 linear）
root.parent_course         string | null                 （shape = branch 时必需）
sections[].probe           {prompt, criteria[{id,text,layer}], hint?}（skeleton 必需）
concepts[].anchor          {path, locator} | "external" | "no-anchor"（skeleton 的 core/supporting 必需）
root.branch_candidates[]   [{id, title, concept_ids[], materials[], work_relevance?, status}]（skeleton 必需、≥1）
coverage[].disposition     + pool | reserve；heading 可为 "*"
```

`lrg_record.py --kind probe`（即时证据，`rigor` 照常）。`learning_state.py defer` 把 unit 写成 deferred（探测通过或学习者要求）。其余脚本对 1.3 的处理与 1.2 相同。

## 8. 与其它规格的关系

- 规格 C 的 `role / check / deferred / outline / units` 在骨架课里全部照用；骨架课的 `units/` 只引用 `pool` 里的 A 级定位，且每个 unit 文档末尾列出"这个原理在你的材料里的落点"（来自 anchor）。
- `docs/consensus.md` §9.3"绝不静默遗漏"在骨架课里的含义变为：每份材料都要有 `pool / reserve / excluded` 之一的去处，而不是每个标题。分支课回到逐标题。
- 知识库：骨架课的 MRG 节点与普通课一样导出；`anchor` 作为概念级 `source_refs` 一并导出，`external` 锚导出为 `support: external`。
