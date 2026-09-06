# Whetstone
> Whetstone 是磨刀石，刀不是靠泡在油里变锋利的。

> "好喜欢知识自然流进脑子里的感觉"　　　　　　　——不懂学习的废物闹麻了

为什么现在的人看个短视频都觉得自己真能学到了知识？网课开个两倍速、论文用 AI 总结成一百字不到、用 agent 就是"继续""报错了""给我能跑的版本"，或许大家都忘记了学习本就应该是对灵魂的鞭笞，对思想的磨练、对肉体的折磨，想轻松为什么不试试垫着书睡觉靠渗透压学会呢（笑）？

这是最难用的学习工具，除非你也想和我成为推动巨石的西西弗斯，否则不建议任何人使用。

---

学习科学几十年反复验证，让学习**感觉**变容易的手段大多损害长期保持，让检索**变费力**的手段大多增强它，这叫 desirable difficulties（必要难度）。主动回忆的元分析效应量 g ≈ 0.5–0.6，自我解释 g ≈ 0.55，而重读接近于零。

## 这是什么

一个由 LLM 驱动的学习系统。你给它书籍、文档或代码库，它把材料转换成一条"问题 → 方案 → 新问题 → 下一方案"的路径，然后逐节要求你主动重建：

- 读到方案之前先预测——"你觉得该怎么解决？"
- 读完合上材料，用自己的话解释概念和机制
- 作答前自评信心，反馈优先曝光"高信心但错误"的地方
- 追问针对你回答里实际暴露的最弱一点，而不是照抄题库
- 下次继续时，先用一道变式题检验上次的理解是否真的留存

反馈受原文证据约束：机器参考图里每一条主张都带来源定位和支持类型（`explicit / entailed / external / pedagogical_inference / unsupported`）。在受信领域（经验证的教材、联网核实过的 CS 知识）参考图是尺子；你可以质疑它的任何一条，系统会出示证据。

系统刻意对你隐瞒两样东西：

- **参考图的高层。** 知识分四层——`fact` 事实、`mechanism` 机制、`rationale` 设计理由、`principle` 设计思想。前两层可读可查；后两层永不展示，只用来出题和判断你的回答到了哪一层。"本质"一旦被总结给你看，就成了又一段要背的东西。
- **你自己的重建日志。** 每次作答只追加、不可改、不可看。你过去的错误主张会以匿名命题的形式回来让你批判——错是你的，尴尬不是。

**项目状态：研究原型。** 核心教学闭环已实现并在日常自用中。v2 设计——持久化知识库（分层机器参考图、只追加的学习者日志、跨课概念注册表与带时效的掌握状态、学科树可视化）——**已实现为可选开启的知识库模式（P0 于 2026-09-05 完成），但尚未在一门真实课程上验证**。规范见 [`docs/specs/`](docs/specs/)，剩余工作（可视化导出、质疑记录、build 管线阶段化）见 [`docs/roadmap.md`](docs/roadmap.md)。[共识文档](docs/consensus.md)末尾列出十八个开放研究问题，它们不应被当作已证明的结论。

## 仓库结构

| 路径 | 内容 |
|---|---|
| [`docs/design.md`](docs/design.md) | 中心思想速览，一页读完 |
| [`docs/consensus.md`](docs/consensus.md) | 规范性基线（v2），规则冲突时的唯一权威 |
| [`docs/learning-layers.md`](docs/learning-layers.md) | 四层理解与不透明原则：系统为什么隐瞒高层 |
| [`docs/specs/knowledge-store.md`](docs/specs/knowledge-store.md) | 持久化知识库定稿：MRG / LRG / 概念索引 / 学习者状态 / 导出（schema 1.1） |
| [`docs/specs/protocol-architecture.md`](docs/specs/protocol-architecture.md) | 协议按状态加载、build 管线、模型分层、eval 集 |
| [`docs/roadmap.md`](docs/roadmap.md) | 当前进度与下一步 |
| [`docs/reviews/`](docs/reviews/) | 学习科学证据评审，带效应量与文献出处 |
| [`plugin/`](plugin/) | 可运行的技能插件，同一份技能目录适配三个宿主 |

文档是这个仓库的一等公民。如果你在构建 AI 学习工具，[共识约束](docs/consensus.md)和[证据评审](docs/reviews/evidence-review.md)可能比代码更有参考价值。

## 安装

同一份技能目录，三个宿主：

| 宿主 | 安装 | 调用 |
|---|---|---|
| Codex | 把 `plugin/` 作为插件安装（含 `.codex-plugin/`） | `$guided-learning-tutor` |
| Claude Code（CLI） | `claude --plugin-dir ./plugin`，或 `claude plugin marketplace add . && claude plugin install guided-learning-tutor@whetstone` | `/guided-learning-tutor:guided-learning-tutor` |
| Claude Desktop（Code 标签页） | 先在终端用上面的命令安装（共用配置），或把 `plugin/skills/*` 复制到 `~/.claude/skills/` | `/guided-learning-tutor` |
| DeepSeek Harness | `cp -r plugin/skills/* ~/.agents/skills/` | `/guided-learning-tutor` |

## 使用

开始一门课：

```text
使用 guided-learning-tutor 技能学习这些材料：
- /path/to/document.md
- /path/to/repository

我希望学完后能够：解释核心设计，并应用到新问题。
```

它会先分析材料、诊断前置知识缺口（一次一题）、必要时联网补充，然后生成课程并逐节教学。中断后重开新会话说"继续我的课程"即可——进度存在学习包的 JSON 里。

遇到不懂的概念：在学习包任何文档里写 `[[概念名]]`，或丢进 `concepts/_inbox.md`，然后调用 `clarify`（Codex 里是 `$clarify`）。它会扫描所有未解决的链接，为每个概念生成一份笔记：解决什么问题、机制、两个例子、边界与常见误解、相关概念双链、回链到教学指南的对应小节。学习包目录用 Obsidian 打开，双链和关系图直接可用。

某一节讲得太粗、想深入：在回答该节主问题前说"想先细化这节"，它会针对本节衍生概念生成一份 `zoom/` 文档，读完再回来答主问题——细化是准备，不替代检验。

本地验证：

```bash
cd plugin && python3 -m unittest discover -s tests
```

纯标准库 Python，无第三方依赖。

## 许可证

[Apache-2.0](LICENSE)
