# Roadmap

本文档记录当前实现相对于整体规划的覆盖情况，以及下一步开发的优先级判断。规则冲突时以 [consensus.md](consensus.md)（v2）为准；数据结构见 [specs/knowledge-store.md](specs/knowledge-store.md)，协议工程见 [specs/protocol-architecture.md](specs/protocol-architecture.md)。

## 六引擎覆盖度（2026-09-05）

| 引擎 | 状态 | 说明 |
|---|---|---|
| Teaching Engine | 基本完成 | 分段揭示、五类针对性追问、反馈顺序、同节不重复出题、信心校准、`--review` 复习不回退位置。缺：按状态加载协议、`depth_reached` 判定、去主体化命题复习。 |
| Knowledge Engine | 约 40% | `lesson-plan.json` 1.0 是线性化的 MRG：每节含 problem / solution / mechanism / concepts / depends_on，`source_refs` 带五类 support。缺：概念 id、类型化关系边、理解层、学科路径、公开层 / 高层分文件。已定稿为 schema 1.1 + `mrg_export.py`。 |
| Assessment Engine | 约 50% | 六维诊断、四种 verdict、隐藏 criteria 在协议中；落盘只有一维 verdict，`criteria_met` 与 `depth_reached` 未持久化，无结构化抽取、无比较器。 |
| Learner Model | 最大缺口 | `attempts[]` 只写不读。无跨课状态、无概念级证据、无时效。已定稿为 `concepts/index.json` + `learner-state.json`。 |
| Curriculum / Policy | 几乎没有 | 顺序在 build 时由 `depends_on` 固定。"变式题替代诊断"与"接缝问题"已定稿，依赖 Learner Model。 |
| Memory Engine | 缺失 | mastered 即永别。v2 用证据等级 × 稳定性的时效窗口占位，不自研遗忘模型。 |

## v2 范围决策的影响

v1 的核心机制是 MRG / LRG 对称比较；它从未运行，且交互成本被评审判定为生死问题。v2 把它收缩为：受信领域内 MRG 默认可信（按支持类型分级），LRG 是只追加、不可见的日志，比较单向。这样做把"验证对称双轨"这个从未有数据的问题换成了三个能立刻产生数据的问题：结构化记录的交互成本、模型判定理解层的可靠性、跨课对齐的精度。

## P0 — 让持久化知识库第一次跑起来

保留插件形态继续教学（在工作的部分不动），全部为本地脚本与文档切分，无服务端。按依赖顺序：

**P0-0 协议按状态拆分**（纯重构，零逻辑变更）
`tutoring-protocol.md` → `references/protocol/{_state-machine,ready,predict,deepen,main,assess,feedback,resume,finish}.md`，每文件 ≤ 40–60 行；`prerequisite-protocol.md` 同法拆三段；SKILL.md 只保留"哪个状态读哪个文件"。先做它，因为它立刻把教学时的有效规则集从约 560 行降到每时刻 ≤ 60 行，并验证三个宿主的渐进加载都可用。

**P0-1 schema 1.1 + `mrg_export.py`**
概念 `id / layer / domain_path / aliases`、顶层 `relations[]`、`criteria[].id`、可选 `principle`；`validate_lesson.py` 同时接受 1.0 / 1.1；导出 `mrg/<id>.json`（公开层）与 `.deep.json`（高层）。用 `examples/project-consensus` 跑通导出。

**P0-2 落盘 `criteria_met` 与 `depth_reached`**
`learning_state.py record` 增加两个字段。三行改动，不做纯属浪费已经完成的诊断。

**P0-3 LRG 结构化记录 + `comparator.py`**
作答后模型输出抽取 JSON（概念状态、关系状态、去主体化命题）；`lrg_record.py` 追加事件到 `lrg/<id>.jsonl`；`comparator.py` 对照 MRG 输出差异清单（`conflict / missing / partial / representation_only / beyond_reference / weak_reference`），不出分数。**同时开始记录每节交互时间**——这是判断 P0-3 是否可承受的唯一指标（阈值 +30%）。

**P0-4 概念注册表 + 学习者状态**
`index_match.py`（别名召回 → 模型确认 → 歧义问学习者）；`learner_state_build.py` 从 `lrg/` 派生 `learner-state.json`（证据等级、稳定性、时效、到达层、错误命题池、仅供着色的估计值）。

**P0-5 变式题替代诊断 + 去主体化复习**
前置阶段查注册表与状态：`fresh / stale` 出变式题（`kind = variant`），`unknown` 走原诊断；resume 与复习从 `error_propositions` 生成"有一种说法是……哪里有问题"。

**P0-6 eval 集**
`plugin/evals/` 三份小材料；build 与 teach 指标见 spec B §6。P0-0 之后、P0-3 之前建好——之后每一步的提示词改动都要能在它上面看到变化。

## P1 — 在 P0 有数据之后

**导出与可视化**：`export_graph.py` → `exports/graph.json` 与 Obsidian 目录（学科路径 = 目录，frontmatter 带时效与掌握估计）。先用 Obsidian graph 看一周，再决定是否做单文件 HTML。

**build 管线阶段化与模型分层**：按 spec B §4 把 build 拆为 S1–S8；Claude Code 上用插件 `agents/*.md` 的 `model` 字段把检索摘要、别名确认交给廉价模型，强模型只做抽取、关系、层标注、评估；其他宿主按文档确认后再做。前提是 P0-6 的 eval 能看出阶段化有没有损害连贯性。

**质疑通道**：`challenges.jsonl` 记录 + MRG 版本化；不做自动裁决。

**跨课接缝问题**：同一 id 二次出现时加载前课 `principle` 层出题（`kind = transfer`）。它是第四层训练的主场合，但要等注册表有两门以上课程的数据。

**网页端 + 第三方模型 API**：仍然排在最后。理由不变——把未验证的教学假设浇进混凝土之前，先用两个脚本证明它值得。

## 已完成

- 2026-08-31：Claude Code / DeepSeek Harness 适配，同一技能目录接三宿主；
- 2026-09-05：`record --review` 修复 resume 复习回退位置的问题；`scan_wikilinks` 支持块列表别名与行内代码；`source_manifest` 分类修正；泄漏检查归一化；CI；
- 2026-09-05：v2 设计定稿（consensus v2、learning-layers、specs/knowledge-store、specs/protocol-architecture）。

## 不做

见 consensus §16.2。特别重申三条：不让学习者查看或编辑 LRG；不展示 `rationale / principle` 层；不对第四层评分。
