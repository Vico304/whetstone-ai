# Whetstone
> Whetstone 是磨刀石，刀不是靠泡在油里变锋利的。

> "好喜欢知识自然流进脑子里的感觉"　　　　　　　——不懂学习的废物闹麻了

为什么现在的人看个短视频都觉得自己真能学到了知识？网课开个两倍速、论文用 AI 总结成一百字不到、用 agent 就是"继续""报错了""给我能跑的版本"，或许大家都忘记了学习本就应该是对灵魂的鞭笞，对思想的磨练、对肉体的折磨，想轻松为什么不试试垫着书睡觉靠渗透压学会呢（笑）？

这是最难用的学习工具，除非你也想和我成为推动巨石的西西弗斯，否则不建议任何人使用。

---

## 这是什么

一个装在 Claude Code、Claude Desktop、Codex、DeepSeek Harness 或 pi 里的学习工具。你给它一本书、一份文档或一个代码库，它把材料重排成一条"问题 → 方案 → 新问题"的路径，然后一节一节地要求你：

- 读到方案之前先预测："你觉得该怎么解决？"
- 读完合上材料，用自己的话讲这一节的概念和机制；
- 作答前给自己的把握打分，反馈先指出"很确定但错了"的地方；
- 追问针对你回答里最弱的一点，不照抄题库；
- 下次继续时，先用一道换了情境的题检查上次学的还在不在。

学习科学几十年的结论是：让学习**感觉**轻松的方法大多损害长期记忆，让回忆**变费力**的方法大多增强它。主动回忆的元分析效应量约 0.5–0.6，自我解释约 0.55，重读接近零（出处见 [`docs/evidence.md`](docs/evidence.md)）。这个工具站在费力的一边。

反馈有依据：课程里每一条说法都记着它来自材料的哪个位置，指出你的错误时会给出位置。

系统故意不给你看两样东西：

- **课程的后两层。** 理解分四层：事实、机制、本质、思想。前两层写在讲义里，可以读、可以查；后两层——为什么这样设计、背后的思想是什么——不展示，只用来出题和判断你的回答到了哪一层。本质一旦被总结给你看，就成了又一段要背的东西。
- **你自己的学习记录。** 每次作答只追加、不可改，系统不会给你看。开启知识库后，你过去的错误说法会在复习时以匿名形式回来让你批判——错是你的，尴尬不是。

## 安装

同一份技能目录，五个环境：

| 环境 | 安装 | 调用 |
|---|---|---|
| Claude Code | `claude plugin marketplace add /path/to/whetstone-ai && claude plugin install whetstone@whetstone-ai`；或临时 `claude --plugin-dir ./plugin` | `/whetstone:learn` 等 |
| Claude Desktop | `python3 package_plugin.py` 生成 `../dist/whetstone.plugin`，在插件管理器上传；或 `./install_skills.sh ~/.claude/skills` | `/learn` 等 |
| DeepSeek Harness | `./install_skills.sh ~/.agents/skills`，重启 `npx @deepseek-ai/dsh web` | `/learn` 等 |
| pi | `pi install git:github.com/Vico304/whetstone-ai`（或本地 `pi install /path/to/whetstone-ai`、`./install_skills.sh ~/.pi/agent/skills`） | `/skill:learn` 等 |
| Codex | 把 `plugin/` 作为插件安装 | `$learn` 等 |

装好后在对话里输入 `/`，看到 `guide / outline / learn / clarify` 四个技能即可。系统写出的一切都放在材料目录下的 `whetstone/` 里，你的材料本身不会被改动。

## 四个技能

| 技能 | 做什么 | 什么时候用 |
|---|---|---|
| **learn** | 总入口。缺什么补什么：你的背景与目标、材料评估、逐门确认的学习计划、本课大纲；确认后逐节生成讲义，检查前置知识，然后逐节教学 | 开一门课，或继续一门课 |
| **guide** | 向导。先问你想了解用法还是规划学习；规划 = 记录背景与目标、评估一个目录里的材料、逐门确认课程序列。只规划，不建课 | 第一次用；材料太多太杂；想改目标或计划 |
| **outline** | 生成、讨论或修改一门课的大纲，确认后写回 | "看看大纲""把第 3 节拆开""改成快速模式" |
| **clarify** | 把你在讲义里标了 `[[双链]]` 的概念写成有来源、多例子的笔记，Obsidian 可直接打开 | 遇到不懂的概念 |

规划时有两个选择：**完整**还是**快速**（快速缩小范围、放宽判定，但仍然先预测后揭示）；**按材料学**还是**按领域学**（按领域学先上一门只讲基本原理的骨架课，你的材料作为例证，学完再从分支里选方向深入）。

## 一个例子

```text
/whetstone:learn 学习 src/threatmodel.adoc，课程目录 whetstone/courses/c2-threatmodel/。
我希望学完能分类陈述敌手模型，并说出每类威胁对应哪个架构机制。
```

它读材料，出大纲，**停下**让你确认；然后逐节生成讲义，检查前置知识（一次一题），开始教学。材料的每个标题都要在大纲里有去处，遗漏会被校验器报错。中断后新开会话说"继续我的课程"。

更多场景（一个目录里有几个仓库和一堆 AI 生成的文档、只改大纲、学习中遇到不懂的概念）见[使用手册](docs/guide.md)。

## 可选：知识库

在你的档案里指定一个目录，课程的参考图和你的学习记录就会跨课累积：下一门课遇到你学过的概念时，用一道变式题代替重新检查；复习时，旧的错误说法以匿名形式回来。

## 状态

1.0，日常可用。知识库是可选功能，尚无长期使用数据。

本地验证：

```bash
cd plugin && python3 -m unittest discover -s tests
```

纯标准库 Python，无第三方依赖。

## 仓库结构

| 路径 | 内容 |
|---|---|
| [`docs/guide.md`](docs/guide.md) | 使用手册 |
| [`docs/design.md`](docs/design.md) | 设计 |
| [`docs/specs/`](docs/specs/) | 课程文件、知识库与教学协议的格式说明 |
| [`docs/evidence.md`](docs/evidence.md) | 学习科学依据与开放问题 |
| [`docs/glossary.md`](docs/glossary.md) | 术语表与写作规则 |
| [`CHANGELOG.md`](CHANGELOG.md) | 更新记录 |
| [`AGENTS.md`](AGENTS.md) | 给 AI 会话的规则：用语、改动边界、提交前检查 |
| [`plugin/`](plugin/) | 可运行的技能插件 |

## 许可证

[Apache-2.0](LICENSE)
