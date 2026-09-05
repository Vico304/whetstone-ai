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

- `schema_version`：当前为 `1.0`；
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
- `concepts`：`name` 与面向学习者的 `explanation`；
- `source_refs`：`path`、`locator`、`support` 与简短 `note`；
- `checkpoint.prompt`、隐藏评估用 `criteria` 和渐进提示 `hint`。

除最后一节外，`new_problem` 应为非空文本。`source_refs.support` 只能是：

```text
explicit | entailed | pedagogical_inference | external | unsupported
```

`unsupported` 只用于记录问题，不得作为稳定讲解的唯一依据。

## `teaching-guide.md`

教学文档面向学习者，不必逐字复制 JSON，但必须同步其顺序与含义：

1. 学习目标、材料范围和阅读方式；
2. 总体问题、系统边界和宏观流程；
3. 问题链预览；
4. 各小节的“问题、方案、机制、意义、代价、新问题、来源、检查点”；
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
