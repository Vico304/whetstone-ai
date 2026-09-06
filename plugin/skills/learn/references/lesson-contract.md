# 教学包契约

## 产物

文件模式的标准教学包包含：

```text
<lesson-id>/
├── sources.json
├── prerequisite-plan.json       # 运行前置检查时创建
├── prerequisite-progress.json   # 前置作答、来源与桥接复测
├── prerequisite-guide.md        # 实际暴露缺口时创建
├── lesson-plan.json
├── teaching-guide.md
├── zoom/                        # 按需细化文档（教学中学习者选择细化时创建）
│   └── <section-id>-guide.md
├── concepts/                    # 概念笔记（clarify 技能维护）
│   ├── _inbox.md
│   └── <概念名>.md
└── learning-progress.json   # 进入教学或需要恢复时创建
```

单一短材料可以省略 `sources.json`，但 `lesson-plan.json` 的 `source_refs` 仍要指向来源。三个 `prerequisite-*` 文件是条件产物：没有实质前置依赖、学习者近期证据已就绪，或用户选择 `skip` 时可以省略。`zoom/` 与 `concepts/` 是按需产物，build 阶段不预生成。纯对话模式可以不创建文件，但应保持同样的逻辑结构。

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

- `schema_version`：新课程写 `1.1`；校验器与导出脚本同时接受 `1.0`（旧课程）；
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
- `source_refs`：`path`、`locator`、`support` 与简短 `note`；
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

## `teaching-guide.md`

教学文档面向学习者，不必逐字复制 JSON，但必须同步其顺序与含义：

1. 学习目标、材料范围和阅读方式；
2. 总体问题、系统边界和宏观流程；
3. 问题链预览；
4. 各小节的"问题、方案、机制、新问题、关键概念、来源、检查点"——**不含**意义、代价、设计思想（它们是 `rationale / principle` 层，留给学习者在回答中自己得出，校验器对 1.1 课程报告逐字出现的意义与代价，并拒绝出现 `principle` 文本）；
5. 总结、整体重述题和迁移挑战；
6. 材料不确定性与进一步阅读。

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
python3 scripts/validate_lesson.py path/to/lesson-plan.json \
  --guide path/to/teaching-guide.md \
  --manifest path/to/sources.json
```

清单不是由脚本生成或路径不能一一对应时可省略 `--manifest`，但仍需人工检查引用是否可定位。校验器检查结构和交叉引用，不证明教学解释本身正确。

## 导出机器参考图（开启知识库时）

校验通过后，把课程导出为分层的机器参考图：

```bash
python3 scripts/mrg_export.py path/to/lesson-plan.json --store <知识库目录> [--manifest path/to/sources.json]
```

产出 `<store>/mrg/<lesson-id>.json`（公开层：`fact / mechanism` 节点与边、各节的问题 / 方案 / 机制骨架）与 `<store>/mrg/<lesson-id>.deep.json`（高层：`rationale / principle` 节点与边、各节的意义、代价、设计思想、检查标准）。**渲染讲义、生成概念笔记、回答学习者查询时只读公开文件；高层文件只在评估与出题时加载。** 已存在的导出不覆盖；修订 MRG 应产生新版本。未开启知识库时不需要此步。
