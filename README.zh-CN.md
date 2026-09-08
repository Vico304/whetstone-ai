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
| [`docs/user-guide.md`](docs/user-guide.md) | **使用手册**：安装、目录约定、一门课的完整流程与示例对话、知识库、排错 |
| [`docs/design.md`](docs/design.md) | 中心思想速览，一页读完 |
| [`docs/consensus.md`](docs/consensus.md) | 规范性基线（v2），规则冲突时的唯一权威 |
| [`docs/learning-layers.md`](docs/learning-layers.md) | 四层理解与不透明原则：系统为什么隐瞒高层 |
| [`docs/specs/knowledge-store.md`](docs/specs/knowledge-store.md) | 持久化知识库定稿：MRG / LRG / 概念索引 / 学习者状态 / 导出（schema 1.1） |
| [`docs/specs/protocol-architecture.md`](docs/specs/protocol-architecture.md) | 协议按状态加载、build 管线、模型分层、eval 集 |
| [`docs/specs/course-planning.md`](docs/specs/course-planning.md) | 先大纲后生成、按 unit 分文档、完整/快速模式、概念角色、覆盖账本（schema 1.2） |
| [`docs/specs/domain-skeleton.md`](docs/specs/domain-skeleton.md) | 学习取向（material / domain）、以证据池为落点的骨架课、原理探测、学习者选择的分支（schema 1.3） |
| [`docs/roadmap.md`](docs/roadmap.md) | 当前进度与下一步 |
| [`docs/reviews/`](docs/reviews/) | 学习科学证据评审，带效应量与文献出处 |
| [`plugin/`](plugin/) | 可运行的技能插件，同一份技能目录适配四个宿主 |

文档是这个仓库的一等公民。如果你在构建 AI 学习工具，[共识约束](docs/consensus.md)和[证据评审](docs/reviews/evidence-review.md)可能比代码更有参考价值。

## 安装

完整的操作手册与示例见 [`docs/user-guide.md`](docs/user-guide.md)。同一份技能目录，四个宿主：

| 宿主 | 安装 | 调用 |
|---|---|---|
| Claude Code（终端 CLI） | `claude plugin marketplace add /path/to/whetstone-ai && claude plugin install whetstone@whetstone-ai`（或临时：`claude --plugin-dir ./plugin`） | `/whetstone:learn` 等 |
| Claude Desktop | 用 `python3 package_plugin.py` 打出 `../dist/whetstone.plugin`，在插件管理器里上传；或 `./install_skills.sh ~/.claude/skills` | `/learn` 等 |
| DeepSeek Harness | `./install_skills.sh ~/.agents/skills`（全局）或 `./install_skills.sh <项目>/.agents/skills`；重启 `npx @deepseek-ai/dsh web` | `/learn` 等 |
| Codex | 把 `plugin/` 作为插件安装（含 `.codex-plugin/`） | `$learn` 等 |

安装后在对话里输入 `/`，能看到 `guide / outline / learn / clarify` 四个技能（描述为中文）即可。系统写出的一切都放在材料根目录下的 `whetstone/`（档案、计划、材料清点、`courses/`、可选的知识库），你的材料目录本身不会被写入。

## 四个技能怎么用

| 技能 | 做什么 | 什么时候用 |
|---|---|---|
| **learn** | 总入口：缺什么补什么（档案 → 材料评估 → 逐门确认计划 → 本课大纲），确认后按 unit 生成文档，前置诊断（骨架课改为原理探测），然后逐节教学 | 开一门课、继续一门课 |
| **guide** | 向导：先问"想知道怎么用，还是规划学习？"；规划 = 学习者档案 + 材料评估（定级 A 一手 / B 自著已核实 / C 生成中间物 / D 噪声）+ 逐门确认的学习计划；只规划不建课 | 第一次用；材料太多太杂；想改目标或计划 |
| **outline** | 生成、讨论、修改一门课的大纲（问题链、全部概念与角色、覆盖账本、模式），确认后写回；不生成 unit、不教学 | 想先看大纲；"把第 3 节拆开""这个概念升成 core""改成快速模式" |
| **clarify** | 把学习包里你标了 `[[双链]]` 的概念写成有来源、多例子的笔记（Obsidian 兼容） | 学习中遇到不懂的概念 |

两条正交的选择在规划阶段决定：**模式** `full`（每个 unit 预测 → 重建 → 追问）/ `fast`（缩范围、容忍模糊，证据打折）；**取向** `material`（学这批材料本身，按标题逐条覆盖）/ `domain`（先学一门只讲基本原理的骨架课，材料作证据池，学完从"分支候选表"选方向深入，每个分支再变成一门普通课）。

### 案例 1：一份规范，直接开课（material 取向）

```text
/whetstone:learn 学习 src/threatmodel.adoc，课程目录 whetstone/courses/c2-threatmodel/。
我希望学完后能分类陈述敌手模型，并说出每类威胁对应哪个架构机制。
```

它读材料 → 出大纲并**停下**让你确认（模式、想略过或加深的 unit）→ 逐 unit 生成 `units/s01.md …` → 前置诊断（一次一题）→ 逐节教学。覆盖账本对照原文每个标题，遗漏会被校验器报错——这就是为什么 CoVE 规范里的 page fault 与时钟中断这类细节不再被"压成一行"。中断后新开会话说"继续我的课程"。

### 案例 2：一个目录里有 3 个仓库 + 十几份 AI 生成的文档（domain 取向）

```text
/whetstone:guide
→ 规划。目录 ~/Project/tee；我想从头巩固可信计算，不只是学 Occlum。
```

向导先记档案（取向定为 domain），扫描目录并定级：上游仓库与官方 docs 是 A 级证据池，你自己写并核实过的方案是 B 级留给分支课，会话总结与交接文档是 C 级**永不作来源**，日志是 D 级排除。计划 = 一门骨架课 + 分支候选表。骨架课大纲里每个概念都标出它在你材料里的**落点**（如 `occlum/docs/fs_overview.md · ## SEFS`），校验器打印落点比例但不设阈值——漂不漂由你判断。确认后先做一轮**原理探测**（每 unit 一道无提示题，答对的 unit 由你决定跳不跳），学完在结课时选分支。

### 案例 3：只改大纲

```text
/whetstone:outline whetstone/courses/c3-refarch/ 把第 5 节拆成两节，"中断与异常的委托路由"升成 core
```

改后重新校验、再确认一次；受影响的 unit 文档标为需重生成，下次 `learn` 处理。

### 案例 4：学习中遇到不懂的概念

在任何 unit 文档里写 `[[G-stage 页表]]`，或丢进 `whetstone/courses/<id>/concepts/_inbox.md`，然后 `/whetstone:clarify`。每个概念得到一份笔记：解决什么问题、机制、两个例子、边界与常见误解、相关概念双链、回链到对应 unit。用 Obsidian 打开 `whetstone/`，双链和关系图直接可用。

某一节讲得太粗、想深入：在回答该节主问题前说"想先细化这节"，它生成一份 `zoom/` 文档，读完再回来答——细化是准备，不替代检验。

### 可选：知识库

在档案里指定一个持久目录，课程的机器参考图（MRG，分层，高层永不展示）与你的学习记录（LRG，只追加、不可见）会跨课累积：下一门课命中你已学过的概念时用变式题代替诊断，快速模式的证据跨课打折，复习时把旧错误去主体化为匿名命题。细节见 [`docs/specs/knowledge-store.md`](docs/specs/knowledge-store.md)。

本地验证：

```bash
cd plugin && python3 -m unittest discover -s tests
```

纯标准库 Python，无第三方依赖。

## 许可证

[Apache-2.0](LICENSE)
