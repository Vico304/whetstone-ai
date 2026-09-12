# 知识库

可选开启的持久化目录。建课时把课程导出为分层的 MRG，教学时把每次作答追加进 LRG，由脚本派生跨课的概念索引和带时效的掌握状态。不开启时插件的行为与单课模式完全相同。实现：`plugin/skills/learn/scripts/` 下的 `store_init.py`、`mrg_export.py`、`index_match.py`、`lrg_record.py`、`comparator.py`、`learner_state_build.py`、`review_pool.py`、`store_sync.py`。

知识库分两层（§8）：每个工作区自己的**本地库**（工作区里的 `store/`，独立布局即 `whetstone/store/`），和汇总各工作区快照的**学习者主目录** `~/.whetstone/`。§1–§7 描述的是本地库；主目录只有索引和派生状态，没有 MRG 正文，也没有 LRG。

## 1. 目录

```text
<store>/
├── store.json                  schema_version、created_at、updated_at、domain_roots[]、lessons[]（每门课的 lesson_id、title、pack_dir、schema_version；前置课另有 prerequisite_of、blocked_at、depth）
├── concepts/index.json         概念索引（§3）
├── mrg/<lesson-id>.json        MRG 公开层：fact / mechanism 节点与边，各节骨架（§2）
├── mrg/<lesson-id>.deep.json   MRG 高层：rationale / principle 节点与边，各节的意义、代价、思想、criteria
├── lrg/<lesson-id>.jsonl       只追加的作答日志（§4）
├── learner-state.json          派生的掌握状态（§5），随时可重建，不手改
└── exports/                    由 init 创建，当前没有脚本写入
```

`mrg/`、`lrg/` 是事实源；`lrg/` 只追加。开启方式：档案的 `knowledge_store=on` 或开课语句里说开知识库；位置固定为工作区内的 `store/`；下文命令以独立布局的 `whetstone/store` 为例。

```bash
python3 scripts/store_init.py init --store whetstone/store [--domain-root 学科名]
python3 scripts/store_init.py register --store whetstone/store --lesson-plan <lesson-plan.json>
```

## 2. MRG：`mrg/<lesson-id>.json` 与 `.deep.json`

`mrg_export.py <lesson-plan> --store <目录> [--manifest sources.json]` 从 lesson-plan 导出，模型不直接写 MRG 文件。两个文件都带 `schema_version: "1.3"`、`lesson_id`、`title`、`shape`、`parent_course`、`branch_candidates`、`grounding`（非骨架课为 `null`）、`generated_at`。

**节点**：`{id, name, aliases[], domain_path[], layer, lesson_id, section_ids[], explanation, source_refs[]}`。公开文件只含 `layer ∈ {fact, mechanism}` 的节点，高层文件只含 `rationale / principle` 的节点。1.0 课程导出时概念 id 由名字生成、`layer` 默认 `mechanism`。

**边**：来自 `relations[]`，`{id, from, to, type, layer, rationale, source_refs[]}`，按 `layer` 分到两个文件。

**节骨架**：公开文件的每节 `{id, title, problem, solution, mechanism, new_problem, concept_ids[], core_concept_ids[], supporting_concept_ids[], listed_concept_ids[], checkpoint_prompt, probe_prompt}`；高层文件的每节 `{id, meaning, tradeoffs[], principle, criteria[], hint, supporting_checks[]}`。

渲染讲义、生成概念笔记、回答学习者查询只读公开文件；高层文件只在评估与出题时加载。已存在的导出不覆盖。

## 3. 概念索引：`concepts/index.json`

```json
{"schema_version": "1.1", "updated_at": "…",
 "concepts": {"cs.tee.certificate-chain": {"name": "证书链", "aliases": ["chain of trust"], "domain_path": ["计算机科学", "可信计算"],
              "appearances": [{"lesson_id": "tee-basics", "section_id": "s03", "layer": "mechanism"}], "created_at": "…"}},
 "alias_index": {"证书链": "cs.tee.certificate-chain", "chain of trust": "cs.tee.certificate-chain"}}
```

**对齐**（建课抽概念时）：

```bash
python3 scripts/index_match.py recall --store <目录> --candidates candidates.json   # [{name, aliases[]}]
```

按归一化名称与别名召回已有 id，每个候选返回 `matches[]`（含该概念的掌握状态）和 `decision_needed`：`none`（无命中，新建）、`confirm_same`（一个命中，模型判断是同一概念还是同名异义、粒度不同）、`disambiguate`（多个命中，问学习者，一次最多三个）。禁止按名称或向量相似自动合并。

**登记**（校验通过、导出之后）：`index_match.py register --store <目录> --lesson-id <id>` 把公开层节点写入索引、追加 `appearances`；别名已指向另一个 id 时只打印 `CONFLICT`，不改指向。

**前置判定**（新课前置检查之前）：

```bash
python3 scripts/index_match.py prerequisites --store <目录> --lesson-id <本课> --prerequisite-plan prerequisite-plan.json
```

| 掌握状态 | `action` | 处理 |
|---|---|---|
| `fresh` | `variant` | 一道变式题代替诊断；答对即 `ready`，答错进正常诊断 |
| `stale` | `variant_then_diagnose` | 先变式题，答错再诊断 |
| `unknown` | `diagnose` | 正常诊断 |
| 概念的 `lessons` 里有本课的前置课（`store.json` 里 `prerequisite_of` 指向本课） | `variant`，附 `via_prerequisite_course` | 不看时效：前置课刚学完只有即时证据，重新诊断会抵消建课的意义 |

只有快速模式证据（`rigor_max: fast`）的 `fresh` 概念按 `stale` 处理。`ambiguous: true` 的项先向学习者确认是不是同一概念。变式题作答记 `--kind variant`。

## 4. LRG：`lrg/<lesson-id>.jsonl`

每行一个事件，只追加。`lrg_record.py append` 运行比较器、追加事件，并通过 `--progress` 同步 `learning-progress.json`：

```bash
python3 scripts/lrg_record.py append --store <目录> --lesson-id <id> --section-id s02 --kind checkpoint \
  --response-file r.txt --feedback-file f.txt --verdict partial --confidence 4 --criteria-met c1,c3 \
  --depth mechanism --extraction extraction.json --progress learning-progress.json --elapsed-seconds 240
```

| 字段 | 含义 |
|---|---|
| `at`、`event: attempt`、`lesson_id`、`section_id`、`attempt_number` | 时间与位置 |
| `kind` | `checkpoint`（主问题与追问）、`supporting`（辅助概念验收，需 `--concept <id>`，不加 `--progress`）、`probe`、`diagnostic`（前置检查的诊断作答）、`bridge`、`review`（resume 变式）、`variant`（跨课或前置课回程的变式题）、`transfer`（迁移题）、`final`（结课整体重述） |
| `evidence_tier` | 由 `kind` 决定：`checkpoint / supporting / probe / diagnostic / bridge` 为 `immediate`，`review / variant` 为 `delayed`，`transfer / final` 为 `transfer` |
| `rigor` | `full / fast`，默认取进度文件的 `mode` |
| `confidence`、`verdict`、`criteria_met[]`、`depth_reached` | 1–5 的信心；`mastered / partial / retry / skipped`；满足的 criteria id；到达的层 |
| `response`、`feedback` | 原文。永不进入任何面向学习者的输出 |
| `target_concept_ids[]` | `--concept` 指定的概念 |
| `elapsed_seconds` | 从提出主问题到判定的墙钟秒数，由模型在前后各运行一次 `date +%s` 得到 |
| `extraction` | 模型对回答的结构化读取，见下 |
| `propositions[]`、`diff`、`feedback_priority[]` | 比较器输出 |

**抽取** `extraction.json`（模板 `assets/extraction-template.json`），`extracted_by: model`：

- `concepts[]`：`{ref, status}`，`ref` 是 id、名称或别名，`status ∈ correct / partial / wrong / missing`；
- `relations[]`：`{from, to, type, status}`，`status ∈ correct / direction_reversed / wrong_type / missing / extra`；
- `propositions[]`：`{text, status, concept_refs[], confidence_high?}`，`text` 是匿名化的原子命题——不含"你说""我认为"，不引用原句；`status ∈ correct / partial / wrong / representation_only`。

学习者不确认、不修改抽取；异议以新一次作答追加。

**比较器** `comparator.py` 对照该课的 MRG（公开层 + 高层 + 索引的别名表）把抽取落成类别，不打分：

| 类别 | 含义 |
|---|---|
| `missing` | 本节 `core` 概念未提及，或参考里有的关系被标 `missing`；supporting 未提及进 `unmentioned_supporting`，listed 永不算缺 |
| `partial` | 概念或命题只说了一部分 |
| `conflict` | 与 `explicit / entailed / external` 支持的参考冲突 |
| `weak_reference` | 与只有 `pedagogical_inference` 支持的参考冲突，不判学习者错 |
| `representation_only` | 只是说法不同，不反馈 |
| `beyond_reference` | 参考里没有的概念、关系或命题，只记录 |
| `unresolved_refs` | 无法映射到概念 id 的名字 |

`feedback_priority` 的顺序：`conflict:high_confidence` → `conflict` → `missing` → `partial` → `weak_reference:do_not_judge_wrong` → `beyond_reference:record_only`。

`lrg_record.py show --store <目录> --lesson-id <id>` 只打印计数与层，不打印回答。

## 5. 掌握状态：`learner-state.json`

`learner_state_build.py build --store <目录>` 从 `lrg/` 与 `mrg/` 重建，每次教学会话结束或 resume 开始时运行。一次作答涉及的概念 = 该节的概念 + `target_concept_ids` + 命题里的概念 + 抽取里以 id 引用的概念。每个概念：

| 字段 | 规则 |
|---|---|
| `evidence_tier` | 最近一次 `mastered` 的 `evidence_tier`；没有则 `none` |
| `last_evidence_at`、`last_success_at`、`last_verdict` | 时间与最近判定 |
| `depth_latest`、`depth_max` | 最近一次与历史最高的 `depth_reached` |
| `stability` | 成功过的不同日期数 |
| `rigor_max` | 成功证据里是否有过 `full` |
| `attempts`、`lessons[]` | 次数与出现过的课程 |
| `freshness` | 最近成功是 `delayed / transfer` 且距今 ≤ 7 × 2^(stability − 1) 天（上限 180）为 `fresh`，超过为 `stale`；只有 `immediate` 证据或无成功为 `unknown` |
| `error_propositions[]` | 状态为 `wrong / partial` 的命题：`{id, text, status, at, lesson_id, section_id}` |
| `calibration` | `overconfident`：`retry` 或高信心冲突且信心 ≥ 4 的次数；`underconfident`：`mastered` 且信心 ≤ 2 的次数 |
| `mastery_estimate` | 证据等级权重（`immediate` 0.4、`delayed` 0.7、`transfer` 1.0）× 时效权重（`fresh` 1.0、`stale` 0.5、`unknown` 0.2）。只供可视化着色，不参与任何教学决策 |

时效窗口是刻意简单的规则，不是遗忘模型。

## 6. 错误复习：`review_pool.py`

```bash
python3 scripts/review_pool.py --store <目录> --lesson-id <id> [--progress learning-progress.json]
```

只读 `learner-state.json`，返回 `error_propositions` 里的命题（`claim`、`status`、`at`、`lesson_id`、`section_id`），`wrong` 在 `partial` 之前、旧的在前；给 `--progress` 时只取已完成的节。呈现固定为："有一种说法是「{claim}」。这个说法哪里有问题？"——不说这是学习者自己说的，不引用原始回答，纠正在同一轮给出。作答记 `--kind review`。答对后命题仍留在池里，由时效自然淘汰。

## 7. 不可见的实现

- 日志不在课程目录里；`lrg_record.py show`、`learner_state_build.py show` 都不打印 `response`；
- 进入提示词的 LRG 内容只有匿名化的命题文本；
- 讲义、概念笔记、学习者查询只读公开层文件；
- 学习者对抽取或判定有异议时追加新一次作答，不修改任何已有记录。

## 8. 学习者主目录：`~/.whetstone/`

为什么分两层：宿主（Claude Code、DeepSeek Harness、Cowork 的连接文件夹）都以当前工作区为信任边界，库放在工作区之外时**每次作答**都会触发一次权限确认。所以每次作答只写本地库；跨工作区的记忆是派生物，头尾各碰一次。

```text
~/.whetstone/                     可用环境变量 WHETSTONE_HOME 改；不存在时由第一次 push 创建
├── home.json                     schema_version、created_at、updated_at
├── workspaces.json               {slug: {path, store, last_push_at, lessons[]}}
├── snapshots/<slug>/index.json           某工作区本地库的 concepts/index.json 副本
├── snapshots/<slug>/learner-state.json   该工作区派生状态的副本
├── concepts/index.json           汇总注册表：同 id 合并 appearances / aliases，每条带 workspaces[]；别名冲突保留先到的并报告
└── learner-state.json            汇总掌握状态（下文）
```

`slug` = 材料根目录名 + 路径哈希前 8 位（如 `tee_dsh-31396d90`）。

```bash
python3 scripts/store_sync.py push --store whetstone/store      # 结课时：重建本地 learner-state → 写快照 → 重算汇总
python3 scripts/store_sync.py rebuild                           # 只从快照重算，不读任何工作区
python3 scripts/store_sync.py show                              # 推过哪些工作区、汇总计数；不打印回答
python3 scripts/index_match.py prerequisites --home --prerequisite-plan …   # 开课前读汇总（一次）
python3 scripts/index_match.py recall --home --candidates …
python3 scripts/review_pool.py --home …                          # 跨工作区取错误主张复习
```

汇总 `learner-state.json` 的每个概念由各工作区快照里的同名概念合并而来：`attempts`、`calibration`、`stability` 相加（稳定性按"不同成功日"计，跨工作区无法去重，取近似）；`lessons`、`error_propositions`（各带 `workspace`）取并集；`depth_max` 取最深；`rigor_max` 有 `full` 即 `full`；`last_evidence_at` / `last_success_at` 取最晚，`evidence_tier` 取最晚一次成功的等级；`freshness` 与 `mastery_estimate` 用合并后的 `stability` 按 §5 的规则在汇总时重算。主目录里没有 `response`、没有 `lrg/`，`show` 也不打印任何回答文本。

宿主在 push 时可能问一次权限；学习者拒绝不影响本课（数据都在本地库），下次结课再推。`--home` 读不到主目录时（还没推过）退回 `--store whetstone/store`。

