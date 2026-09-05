# 设计定稿 A：持久化知识库（MRG / LRG / 概念索引 / 学习者状态）

> 文档性质：规范性设计定稿（schema 1.1）。实现前的权威描述；实现落地后，以脚本与校验器为准，本文档同步修订。
> 状态：已定稿，待实现（见 [roadmap.md](../roadmap.md) P0）。
> 上位文档：[consensus.md](../consensus.md)（冲突时以共识为准）；理念背景见 [learning-layers.md](../learning-layers.md)。

---

## 0. 一句话

在学习包之外新增一个**可选开启**的持久化目录（知识库 store）。build 时把课程结构导出为有来源、分层的机器参考图（MRG）；教学时把学习者每一次作答按概念、关系、命题和理解深度追加进不可编辑、对学习者不可见的重建日志（LRG）；由脚本从两者派生出跨课的概念索引、带时效的学习者状态和可视化导出。

## 1. 设计决策（已定）

| # | 决策 | 取代的旧表述 |
|---|---|---|
| D1 | **MRG 是有来源的正确知识框架。** 在受信领域（经验证的理工教材、经联网核实并标 `external` 的计算机科学知识），MRG 默认可信，是诊断的尺子 | "机器参考不等于真理，两图冲突回到原文裁决，任何一方都可能错" |
| D2 | 可信按支持类型分级：`explicit` > `entailed` > `external` > `pedagogical_inference`。诊断时 `pedagogical_inference` 边降权；学习者与之冲突不直接判错 | 无分级 |
| D3 | **LRG 是 append-only 的过程日志**。学习者不可编辑；系统不覆盖；任何异议以新一次作答追加 | LRG 可由学习者修订、拆分、合并 |
| D4 | **LRG 对学习者完全不可见。** 系统可以用旧回答出题，但以去主体化的匿名命题呈现，原文永不进入提示词 | 学习者可查看自己的重建 |
| D5 | **MRG 分层，高层不透明。** 节点与边带 `layer ∈ {fact, mechanism, rationale, principle}`；学习者主动查询只能触及 `fact` 与 `mechanism`；`rationale` 与 `principle` 物理分文件，仅在评估与出题时加载 | 无分层 |
| D6 | 双图关系由"对称比较、互相纠错"改为**单向诊断比较**：LRG 对照 MRG 产出差异清单；对 MRG 的质疑是一等事件但低优先级通道 | 双轨对称 |
| D7 | 跨课复用：概念注册表 + alias 召回 + 模型语义确认 + 歧义时问学习者一句；命中后**用一道变式检索题替代完整前置诊断**，不跳过 | 无 |
| D8 | "已掌握"必须带时效。证据等级 × 距今时间 → `fresh / stale / unknown` | 无 |
| D9 | 可视化主视图是学科层级树，节点可展开邻接；节点颜色深浅 = **当前掌握估计**（证据等级 × 时效），不是历史错误次数 | 无 |
| D10 | 学科路径 `domain_path` 由模型 build 时推断；用户修改路径暂不实现 | 无 |
| D11 | 第四层（感悟 / 三观）只记录、不评分、不着色 | 无 |

D1、D6 是**范围决策**，不是研究结论：项目当前只面向受信材料。将来面对可信度未知的材料时，需重新启用 consensus §10.4 的对称裁决表，本文档 §7 预留了通道。

## 2. 目录布局

```text
<store>/                         # 用户指定；默认不开启
├── store.json                   # schema_version、created_at、默认学科根、开启的课程列表
├── concepts/
│   └── index.json               # 概念注册表（§4）
├── mrg/
│   ├── <lesson-id>.json         # 公开层：fact / mechanism 节点与边（§3）
│   └── <lesson-id>.deep.json    # 高层：rationale / principle；仅评估与出题时加载
├── lrg/
│   └── <lesson-id>.jsonl        # append-only 事件日志（§5）
├── learner-state.json           # 派生：按概念汇总的多维状态（§6）
├── challenges.jsonl             # 对 MRG 的质疑事件（§7）
├── reflections.jsonl            # 第四层：记录不评分（§8）
└── exports/                     # 派生：可视化导出（§9）
    ├── graph.json
    └── obsidian/
```

- 学习包目录（`teaching-guide.md`、`lesson-plan.json`、`learning-progress.json` 等）**不变**，store 是增量；未开启 store 时插件行为与 v0.2 完全一致。
- `learner-state.json` 与 `exports/` 是派生物，随时可由 `lrg/` + `concepts/index.json` 重建；不手改。
- `mrg/*.json`、`lrg/*.jsonl`、`challenges.jsonl`、`reflections.jsonl` 是事实源；`lrg/` 与两个 `.jsonl` 只追加。

## 3. MRG：`mrg/<lesson-id>.json` 与 `.deep.json`

### 3.1 节点

```json
{
  "id": "cs.trusted-computing.certificate-chain",
  "name": "证书认证链",
  "aliases": ["证书链", "chain of trust", "信任链"],
  "domain_path": ["计算机科学", "可信计算"],
  "layer": "mechanism",
  "lesson_id": "tee-basics",
  "section_ids": ["s03"],
  "explanation": "面向学习者的一段解释（仅 fact / mechanism 层）",
  "source_refs": [
    {"path": "book/ch4.md", "locator": "§4.2 第 3 段", "support": "explicit", "note": "定义与链式验证顺序"}
  ]
}
```

- `id`：`<domain-slug>.<concept-slug>`，跨课程稳定；由 §4 的匹配流程决定是复用还是新建。
- `layer`：`fact`（定义、事实、术语）/ `mechanism`（如何工作、输入如何变输出）/ `rationale`（为什么这样设计、代价与取舍）/ `principle`（跨情境可迁移的设计思想）。
- `.json` 只含 `layer ∈ {fact, mechanism}` 的节点；`.deep.json` 只含 `rationale`、`principle` 节点，以及从 lesson-plan 的 `meaning`、`tradeoffs` 提炼出的高层内容。**渲染 teaching-guide、clarify 概念笔记、学习者主动查询，一律只读 `.json`。**

### 3.2 边

```json
{
  "id": "e017",
  "from": "cs.trusted-computing.root-of-trust",
  "to": "cs.trusted-computing.certificate-chain",
  "type": "enables",
  "layer": "mechanism",
  "rationale": "链的每一环都由上一环签名，最终锚定在硬件根信任",
  "source_refs": [{"path": "book/ch4.md", "locator": "§4.2", "support": "explicit", "note": "…"}]
}
```

- `type` 取自受控集合（consensus §6.4）：`is_a | part_of | depends_on | causes | enables | implements | contrasts_with | instance_of | prerequisite_for`。`prerequisite_for` 默认 `support = pedagogical_inference`。
- 所有边有向；`contrasts_with` 记为双向。
- 学科层级不用显式边存，由 `domain_path` 派生（§9）。
- `.deep.json` 的边同样带 `layer ∈ {rationale, principle}`，典型如"X 相对 Y 的取舍"（`contrasts_with` + rationale）、"X 与另一门课的 Z 共享同一设计思想"（`principle` 层跨课边，见 §4.4）。

### 3.3 与 `lesson-plan.json` 的关系（schema 1.0 → 1.1）

MRG 由 `mrg_export.py` 从 lesson-plan 导出，不由模型直接写 MRG 文件。为此 lesson-plan 升到 1.1：

| 字段 | 1.0 | 1.1 |
|---|---|---|
| `sections[].concepts[]` | `name`, `explanation` | 增加 `id`、`layer`、`domain_path`、`aliases` |
| 顶层 `relations[]` | 无 | 新增：概念间有类型有方向的边（§3.2 结构，`from`/`to` 用概念 id） |
| `sections[].meaning`、`tradeoffs` | 面向学习者展示 | 仍保留，但导出时归入 `.deep.json`（rationale 层）；teaching-guide 只渲染 `problem / solution / mechanism` 与 `new_problem`，`meaning` 与 `tradeoffs` 改为主问题与追问的素材 |
| `sections[].principle` | 无 | 可选：本节体现的可迁移设计思想（`principle` 层，只进 `.deep.json`） |
| `checkpoint.criteria[]` | 字符串数组 | 对象数组 `{id, text, layer}`，使 `criteria_met` 可引用，并让评估知道每条标准对应哪一层 |
| `schema_version` | `"1.0"` | `"1.1"` |

校验器同时接受 1.0 与 1.1；1.0 文件导出时概念 id 由 slug 生成、`layer` 默认为 `mechanism`、无 `relations`。

## 4. 概念注册表：`concepts/index.json`

```json
{
  "schema_version": "1.1",
  "concepts": {
    "cs.trusted-computing.certificate-chain": {
      "name": "证书认证链",
      "aliases": ["证书链", "chain of trust", "信任链"],
      "domain_path": ["计算机科学", "可信计算"],
      "appearances": [
        {"lesson_id": "tee-basics", "section_id": "s03", "layer": "mechanism"},
        {"lesson_id": "tls-deep-dive", "section_id": "s02", "layer": "mechanism"}
      ],
      "created_at": "2026-09-05T10:00:00Z"
    }
  },
  "alias_index": {"证书链": "cs.trusted-computing.certificate-chain", "chain of trust": "…"}
}
```

### 4.1 匹配流程（build 阶段）

```text
模型提出候选概念（name + aliases + 初判 domain_path）
  → index_match.py 按 alias / 归一化名称召回已有 id（确定性）
  → 模型对每个召回项做语义确认："同一概念 / 同名异义 / 粒度不同（上下位）"
  → 明确同一 → 复用 id，追加 appearance
  → 明确不同 → 新建 id（允许同名不同 domain）
  → 模型无法确定 → 向学习者问一句（一次最多 3 个歧义项），不阻塞其余构建
```

禁止按名称或向量相似度自动合并（consensus §18.3 不变）。向量相似度将来只用于召回。

### 4.2 对前置诊断的影响

新课 build 时，前置候选概念先查注册表与 `learner-state.json`：

| 学习者状态 | 前置处理 |
|---|---|
| `fresh`（近期有延迟或迁移证据） | 一道变式检索题替代诊断；答对即通过 |
| `stale`（有证据但已过期） | 一道变式检索题；答错则进入正常诊断 |
| `unknown`（无记录） | 正常前置诊断（prerequisite-protocol 不变） |

变式题作答以 `kind = "variant"` 记入 LRG，使跨课复用同时成为一次间隔复习。

### 4.3 学科路径

`domain_path` 由模型在 build 时推断，浅层（建议 2–3 级，最多 4 级），首级尽量取自 `store.json` 的默认学科根列表。属于 `pedagogical_inference`，允许错；错的代价只是树的位置，不影响正确性。用户修改路径的机制（改 JSON 或改 Obsidian 目录位置反向同步）**本版本不实现**。

### 4.4 跨课接缝

同一 id 在第二门课再次出现时，评估阶段可加载该概念在前一门课的 `principle` 层内容，生成"接缝问题"（"这里的 X 和你之前学的 Y 是同一个设计思想吗？差在哪？"）。接缝问题是训练第四层理解的主要场合（见 [learning-layers.md](../learning-layers.md) §4），其作答以 `kind = "transfer"` 记录。

## 5. LRG：`lrg/<lesson-id>.jsonl`

每行一个事件，只追加。核心事件 `attempt`：

```json
{
  "at": "2026-09-05T10:12:33Z",
  "event": "attempt",
  "lesson_id": "tee-basics",
  "section_id": "s03",
  "kind": "checkpoint",
  "attempt_number": 2,
  "confidence": 4,
  "verdict": "partial",
  "criteria_met": ["c1", "c3"],
  "depth_reached": "mechanism",
  "response": "学习者原文，永不进入后续提示词",
  "feedback": "当次反馈原文",
  "extraction": {
    "extracted_by": "model",
    "concepts": [
      {"id": "cs.trusted-computing.certificate-chain", "status": "correct"},
      {"id": "cs.trusted-computing.root-of-trust", "status": "missing"}
    ],
    "relations": [
      {"from": "…root-of-trust", "to": "…certificate-chain", "type": "enables", "status": "direction_reversed"}
    ],
    "propositions": [
      {"id": "p-7f3a", "text": "证书链的验证从叶证书开始向根方向逐级签名", "status": "wrong", "concept_ids": ["…certificate-chain"]}
    ]
  },
  "diff": {
    "missing": ["…root-of-trust"],
    "conflict": ["p-7f3a"],
    "representation_only": [],
    "beyond_reference": [],
    "weak_reference": []
  }
}
```

字段约定：

- `kind`：`checkpoint`（本节主问题与追问）/ `review`（resume 开场变式）/ `variant`（跨课前置替代题）/ `transfer`（迁移题、接缝题）/ `bridge`（前置补充后的桥接复测）/ `final`（课程结束整体重述）。即时证据 = `checkpoint`；延迟证据 = `review`、`variant`；迁移证据 = `transfer`、`final`。
- `depth_reached`：本次作答实际到达的层，`fact | mechanism | rationale | principle`，由评估模型判定；它是**层**不是**对错**——一个到达 `rationale` 但有一处事实错误的回答，`verdict = partial`、`depth_reached = rationale`。
- `extraction`：模型对自由文本的结构化读取，是**派生视图**，必须标 `extracted_by`。学习者不确认、不修改；若学习者在下一轮反驳抽取结果，那是新的 `attempt`。
- `propositions[].text`：**去主体化**的命题（不含"你说""我认为"，不引用学习者原句），是唯一允许进入未来提示词的 LRG 内容。复习题从 `status ∈ {wrong, partial}` 的命题生成："有一种说法是……，这个说法哪里有问题？"
- `diff`：比较器输出的差异清单（§5.1），不出分数。

### 5.1 比较器 `comparator.py`

输入：本次 `extraction` + 该节 MRG 公开层与高层。输出 `diff`，类别取 consensus §10.2 的子集：

| 类别 | 含义 | 反馈优先级 |
|---|---|---|
| `conflict` | 学习者命题与 `explicit / entailed` 边冲突，或关系方向相反 | 最高（高信心时更高） |
| `missing` | 该节 MRG 概念或关键边未被提及 | 高 |
| `partial` | 概念提到但机制未说清 | 中 |
| `representation_only` | 仅表述不同，语义一致 | 不反馈 |
| `beyond_reference` | 学习者新增且 MRG 没有的合理联系 | 记录，不判错；可能成为 `challenges` 或个人扩展 |
| `weak_reference` | 冲突对象是 `pedagogical_inference` 边 | 不判学习者错；记录，供人工复核 MRG |

概念对齐用 id 与 alias（确定性）；命题拆分与语义比对由模型完成；类别归属由脚本按规则落定。比较器不产出总分，`verdict` 仍由评估模型综合判定。

### 5.2 不可见原则的实现

- LRG 文件不在学习包目录，学习者日常不会碰到；
- `learning_state.py show` 只显示小节状态与次数，不显示回答；
- 任何面向学习者的输出（讲义、概念笔记、复习题、可视化）不得包含 `response` 原文；校验器对 `exports/` 做逐字与归一化子串检查（复用 `validate_lesson.py` 的泄漏检查）。

## 6. 学习者状态：`learner-state.json`（派生）

由 `learner_state_build.py` 从 `lrg/*.jsonl` 与 `concepts/index.json` 重建：

```json
{
  "generated_at": "…",
  "concepts": {
    "cs.trusted-computing.certificate-chain": {
      "evidence_tier": "delayed",
      "last_evidence_at": "2026-09-01T…",
      "last_verdict": "mastered",
      "depth_latest": "mechanism",
      "depth_max": "rationale",
      "stability": 3,
      "freshness": "fresh",
      "error_propositions": ["p-7f3a"],
      "calibration": {"overconfident": 1, "underconfident": 0},
      "mastery_estimate": 0.72
    }
  }
}
```

- `evidence_tier`：该概念**最近一次**成功证据的等级：`immediate < delayed < transfer`。
- `stability`：跨时间成功重建的次数（同一天内多次只计一次）。
- `freshness`：`fresh` 若最近一次延迟或迁移证据距今 ≤ `7 × 2^(stability−1)` 天（上限 180 天）；超过为 `stale`；只有即时证据或无记录为 `unknown`。这是一个刻意简单的规则，不是遗忘模型；将来若接 FSRS，替换这一个函数即可。
- `mastery_estimate ∈ [0,1]`：**只供可视化着色**的标量 = 等级权重（immediate 0.4 / delayed 0.7 / transfer 1.0）× 时效衰减（fresh 1.0 / stale 0.5 / unknown 0.2）。多维字段仍全部保留；此标量不参与任何教学决策（consensus §10.3 不变）。
- `error_propositions`：指向 LRG 中 `wrong / partial` 命题的 id，是复习题池。

## 7. 质疑 MRG：`challenges.jsonl`

```json
{"at": "…", "lesson_id": "…", "target": "e017", "learner_claim": "去主体化后的主张", "evidence": [{"path": "…", "locator": "…"}], "status": "open"}
```

- 学习者可在任何时候对 fact / mechanism 层内容提出质疑；系统按 D2 分级回应：`explicit` 出示原文定位；`external` 出示来源与 `accessed_at`；`pedagogical_inference` 直接承认为教学推断。
- 质疑被接受时不改原 MRG 文件，生成 `mrg/<lesson-id>.v2.json`（新版本），`store.json` 记录当前版本号。
- 本版本不实现自动比对质疑与 MRG；质疑的裁决由用户在对话中完成，脚本只负责记录与版本化。将来面对可信度未知的材料时，在此通道上启用 consensus §10.4 的对称裁决表。

## 8. 第四层：`reflections.jsonl`

```json
{"at": "…", "concept_ids": ["…"], "lesson_id": "…", "text": "学习者对设计思想 / 跨领域联系的自述", "prompted_by": "transfer-q-…"}
```

只追加、不评分、不进入 `learner-state.json`、不影响着色。可以被系统拿来出题（"你三个月前对 X 的这个想法，现在还成立吗？"），此时以去主体化方式呈现与 §5 相同。

## 9. 可视化导出：`exports/`

### 9.1 `graph.json`

```json
{
  "nodes": [{"id": "…", "name": "…", "domain_path": ["计算机科学", "可信计算"], "layer": "mechanism", "mastery_estimate": 0.72, "freshness": "fresh", "evidence_tier": "delayed", "depth_max": "rationale", "lessons": ["tee-basics"]}],
  "hierarchy": [{"from": "计算机科学", "to": "计算机科学/可信计算"}, {"from": "计算机科学/可信计算", "to": "cs.trusted-computing.certificate-chain"}],
  "edges": [{"from": "…", "to": "…", "type": "enables"}]
}
```

- `hierarchy` 由 `domain_path` 派生；`edges` 只含公开层的边（高层不导出）；
- 主视图沿 `hierarchy` 画树，选中节点后沿 `edges` 展开一跳邻接；
- 颜色：`mastery_estimate` 映射到单一色相的深浅，越深越高；`unknown` 用中性灰而不是浅色；
- 不导出任何 LRG 原文；`error_propositions` 只导出数量。

### 9.2 Obsidian 导出

`exports/obsidian/<domain>/<subdomain>/<概念名>.md`，frontmatter 含 `id`、`aliases`、`domain_path`、`evidence_tier`、`freshness`、`depth_max`、`last_evidence_at`、`mastery_estimate`；正文取公开层 `explanation` 与来源定位；正文中用 `[[概念名]]` 表达公开层的边。目录即学科树，Obsidian graph 的颜色分组按 `freshness` 配置即可，无需自建前端。与 clarify 技能维护的学习包内 `concepts/` 目录互不覆盖。

## 10. 与现有脚本的关系

| 新脚本 | 职责 | 依赖 |
|---|---|---|
| `store_init.py` | 创建 store 目录与 `store.json`，登记课程 | — |
| `mrg_export.py` | lesson-plan 1.0/1.1 → `mrg/<id>.json` + `.deep.json` | `validate_lesson.py` 通过 |
| `index_match.py` | 候选概念 → 召回已有 id；写入 appearance | `concepts/index.json` |
| `lrg_record.py`（或扩展 `learning_state.py record`） | 追加 `attempt` 事件；同时维持 `learning-progress.json` 兼容 | 抽取 JSON 由模型提供 |
| `comparator.py` | 抽取 + MRG → `diff` | `mrg/`、抽取 JSON |
| `learner_state_build.py` | `lrg/` + `index` → `learner-state.json` | — |
| `export_graph.py` | → `exports/graph.json` 与 Obsidian 目录 | `learner-state.json` |

全部标准库 Python；全部有单元测试；`validate_lesson.py` 增加对 1.1 字段、`relations[]` 端点存在性、`layer` 枚举、`criteria[].id` 唯一性的检查，并对导出物做 LRG 原文泄漏检查。

## 11. 不做的事（本版本）

- 不做图数据库、不做服务端、不做多用户；
- 不做 FSRS 级遗忘模型（§6 的 freshness 规则是占位）；
- 不做自动 MRG 修订；不做质疑的自动裁决；
- 不做用户改学科路径；
- 不做自建可视化前端（先用 Obsidian；`graph.json` 为将来的单文件 HTML 预留）；
- 不把 `mastery_estimate` 用于任何教学决策。
