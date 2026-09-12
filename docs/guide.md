# Whetstone 使用手册

只讲怎么用。为什么这样设计见 [design.md](design.md)，文件格式见 [specs/](specs/)。示例对话为示意，实际措辞以会话为准。

## 1. 它是什么、不是什么

Whetstone 把你给它的材料（教材章节、规范、代码库、论文）重排成一条"问题 → 方案 → 新问题"的路线，然后要你逐节自己讲：先预测，再读方案，合上材料用自己的话解释，给把握打分，被追问，再答。它记下你每一次作答，包括错的；开启知识库后，还跨课记录你对每个概念的掌握和有效期。

它不是摘要器、闪卡生成器或问答机器人。它不会把"本质"讲给你听：为什么这样设计、背后的思想是什么，这两层只用来出题和判断你的回答到了哪一层。

适合想真正掌握一份技术材料的人；只要结论的人不适合——快速模式也要你自己讲，只是范围小、判得松。

## 2. 安装

**Claude Code**

```bash
claude --plugin-dir /path/to/whetstone-ai/plugin        # 只对本次会话生效
claude plugin marketplace add /path/to/whetstone-ai      # 持久安装
claude plugin install whetstone@whetstone-ai
```

新开会话输入 `/`，应看到 `whetstone:guide`、`whetstone:outline`、`whetstone:learn`、`whetstone:clarify`。检查：`cd plugin && python3 -m unittest discover -s tests`，应全部通过。

**Claude Desktop**：Code 标签页不支持 `/plugin` 命令，在终端按上面的方式装好即可（共用 `~/.claude/`）。聊天模式：仓库根目录运行 `python3 package_plugin.py` 生成 `../dist/whetstone.plugin`，在插件管理器上传。这时插件在云端，你的材料、课程目录和知识库在本地连接的文件夹里，开课时把本地路径说清楚；脚本会被复制到 `whetstone/scripts/` 本地执行。

**不走插件机制**：`./install_skills.sh ~/.claude/skills`，调用名去掉前缀（`/learn` 等）。

**Codex**：把 `plugin/` 作为插件安装，调用 `$guide`、`$outline`、`$learn`、`$clarify`。

**DeepSeek Harness**：`./install_skills.sh ~/.agents/skills`（全局）或 `./install_skills.sh <项目>/.agents/skills`（项目级，目录里要有 `.git`）。四个技能必须平铺在同一个根目录下，guide 和 outline 会引用同级的 learn。启动 `npx @deepseek-ai/dsh web`（Node 22.19 以上），打开 http://127.0.0.1:3080 ，首次在 Settings → Models 填 API key，用 Choose workspace 选中工作目录；重启后在 `/` 面板的 Skills 组里能看到。

**pi**：`pi install git:github.com/Vico304/whetstone-ai`（根目录 `package.json` 的 `pi.skills` 指向 `plugin/skills`），或本地 `pi install /path/to/whetstone-ai`，或 `./install_skills.sh ~/.pi/agent/skills`；pi 也读 `~/.agents/skills`，装过 DeepSeek Harness 那份就不用再装。调用 `/skill:learn` 等。

## 3. 目录

系统写出的一切都放在一个工作区里，你的材料本身不会被写入。工作区有两种布局：

**独立布局**：打开材料目录就地学，工作区是它下面的 `whetstone/`。
**统一布局**：建一个总目录，材料放在 `material/` 下，用工具打开这个总目录；工作区就是它，课程按学习目标分组放在 `courses/<目标>/`，一个 `store/` 管所有课。已有的 `whetstone/` 可以整个搬进去——课程目录自己记着材料根在哪，搬完照常校验。

```text
统一布局：
<总目录>/
├── material/<材料集>/ …       你的材料，原样不动
├── learner-profile.md         跨目标的背景与偏好
├── courses/<目标>/            每个学习目标一个：learning-plan.md、survey/、各课程目录
├── external/<集名>_<日期>/    系统检索来的外部资料存档
└── store/

独立布局：
<材料根>/
├── occlum/ 文档/ …            你的材料，原样不动
└── whetstone/                 工作区，可以整个搬走、备份、用 Obsidian 打开
    ├── learner-profile.md     你的背景与目标，跨课，你可以读和改
    ├── learning-plan.md       课程序列
    ├── survey/                材料清点
    ├── courses/<课程>/
    │   ├── outline.md         路线图、全部概念、覆盖表 —— 读
    │   ├── units/s01.md …     每节的讲义 —— 读
    │   ├── zoom/              按需细化的文档
    │   ├── concepts/          clarify 生成的概念笔记
    │   ├── lesson-plan.json   机器计划，含不展示的判定标准
    │   ├── sources.json       来源清单
    │   └── learning-progress.json   进度和你的原始回答 —— 不要打开
    ├── external/<集名>_<日期>/  系统检索来的外部资料存档
    ├── store/                 知识库，可选
    └── scripts/               只在 Claude Desktop 聊天模式下出现
```

系统在三种情况下会自己检索可靠的外部资料：建前置课、补骨架课里在你材料中找不到落点的概念、材料只说"是什么"没说"为什么"的机制。检索到的先存进 `external/`，每集一份 `_index.md` 记来源、发布方、访问时间和选它的理由；引用时标为外部知识，不用它们改写你材料的说法；校验器打印外部引用的比例，没有阈值。课程里所有路径都相对材料根，`sources.json` 记录材料根相对课程目录的位置，校验时不必再给 `--sources-root`；旧课程目录里写的是 `"."` 时运行一次 `python3 $S/source_manifest.py --rebase <课程目录>/sources.json --base <材料根>`。

## 4. 一门课的流程

```text
/whetstone:learn 材料 + 目标 [+ 开知识库]
    ↓  没有档案 → 问一轮背景与目标；材料是目录或太大 → 清点、切成计划、逐门确认（也可单独 /whetstone:guide）
    ↓  本课大纲：问题链 + 全部概念 + 覆盖表（也可单独 /whetstone:outline）
    ★  停下：你确认模式（完整 / 快速）和取舍
    ↓  逐节生成 units/<id>.md
    ↓  前置检查，一次一题；骨架课改为探测题
    ↓  有缺口 → 为它们建一门前置课（外部资料、和主课一样确认大纲、逐节教、记录），学完回到主课卡住的那一节
    ↓  逐节教学：预测 → 揭示 → [细化] → 打分 → 作答 → 追问 → 记录
    ↓  结课：不看顺序重述整条问题链 + 迁移题
中断后：新会话说"继续我的课程" → 先一道变式题 → 回到未完成的节
```

**前置课。** 前置检查（或骨架课的探测题）发现你缺的不是一两个词而是一层基础时，系统不写补充文档，而是为这些缺口建一门课：来源是它检索并存档的外部资料，模式和主课相同，大纲同样要你确认，逐节教、逐节记录。主课在卡住的那一节等着；前置课学完，系统对那几个概念出变式题，然后从卡住的节继续。前置课自己也可能再建一层。你在哪一层、离回到主课还差什么，随时在 `learning-plan.md` 的"前置栈"里能看到。自述"基础薄弱"时探测题不能跳过——它量的是你的地板在哪。

**选材料。** 第一门课用一章教材或一个模块，30 KB 以内，能切 4–6 节。整本书会得到很长的大纲，先挑一段。代码库先给入口和主流程所在的目录。

**开课。** 档案已有、材料是单个小文件时，一句话就到大纲；否则最多三轮：背景与目标、（材料是目录时）逐门确认计划、确认大纲。

```text
/whetstone:learn 学习 /Users/me/materials/cove-ch4-attestation.adoc，
课程目录 /Users/me/materials/whetstone/courses/cove-attestation/，开知识库。
我希望学完后能解释远程证明为什么需要信任链，并能判断一个新方案的信任根在哪。
```

不说开知识库就是单课模式。

**确认大纲。** 它停下来，给你 `outline.md` 的路径和摘要，只问一件事：模式，以及想略过或加深的节。回答示例：`完整，就这样`；`快速，略过 4 和 6`；`完整；把"DICE 层级"升成核心概念；第 3 节我熟，略过`；`你定`（等于完整、不略过）。这是你唯一需要"规划"的时刻。

**逐节学。** 每节五步，一次只推进一步：预测（只给"当前问题"，说个方向，不判分）→ 揭示（方案与机制，对照你的预测评一句；这时可以要求先细化本节）→ 报 1–5 的把握并用自己的话回答主问题 → 追问（针对最弱的一点，边界、反例、因果、删除、对比之一，最多两层）→ 记录，下一节。想验收某个辅助概念，任何时候说"验收 X"。

**中断与继续。** 新会话说"继续我的课程"并给出课程目录。它先出一道变式题——换情境考已学过的同一机制——或从你过去的错误说法里取一条以匿名形式让你批判，再回到未完成的节。

## 5. 示例

材料设为一份 RISC-V 保密计算规范的"远程证明"章节。

### 5.1 确认大纲

> **模型**：大纲已生成：`whetstone/courses/cove-attestation/outline.md`。推断的目标：解释远程证明为什么需要信任链，并能判断新方案的信任根在哪。共 5 节：
> 1. 为什么 host 说的话不能信 → 用硬件根信任签名的测量
> 2. 测量什么、何时冻结 → measured pages 与 finalize
> 3. 谁来签、密钥从哪来 → 逐层派生（DICE）而非固定密钥
> 4. 依赖方怎么验 → 证书链与 evidence 格式
> 5. 哪些攻击不在范围内 → 威胁模型边界
>
> 概念共 19 个：核心 9、辅助 6（含"TVM 退出路径""zero pages"）、仅列出 4（各 SBI 函数名、CDDL 字段）。覆盖表：`attestation.adoc` 全部标题已分配；`appendix_b.adoc` 的错误码表不讲，与目标无关。
>
> 两个决定请你定：完整还是快速？想略过或加深的节、想升成核心的概念？

> **你**：完整。第 5 节我做过威胁建模，略过；"TVM 退出路径"升成核心。

> **模型**：已写回：完整模式；第 5 节略过（理由：你已有经验）；"TVM 退出路径"改为第 2 节的核心概念。正在生成 4 份讲义……全部通过校验。开始前置检查，一次一题。第一题——

### 5.2 前置检查：学过的概念

> **模型**：概念索引里有你上门课学过的"G-stage 页表"，12 天前的延迟证据，仍在有效期。不重新检查，出一道变式题代替：**如果 host 能改 G-stage 页表，TVM 的哪一条保证最先失效？**

> **你**：内存隔离。host 把 TVM 的页映射到自己的地址空间就能读。

> **模型**：对。这一项通过。下一项"测量"没有记录，正常检查——

### 5.3 一节的完整回合

> **模型**：**第 2 节 · 当前问题**：依赖方要验证 TVM 的初始状态，但 TVM 是由不可信的 host 一页一页搭起来的。你觉得该测量什么、在什么时候停止测量？说个方向，不判分。

> **你**：测量所有加载的页，创建完成时停。

> **模型**：方向对，"什么时候停"正是规范设计的关键。方案与机制见 `units/s02.md`：页分两类——measured pages 拷贝并计入测量，zero pages 清零不计入；`finalize` 是测量提交点。本节还有 `[[NACL 共享内存]]`、`[[promote_to_tvm]]` 等只列出的概念，想先细化哪一个，还是直接回答本节问题？

> **你**：直接答。

> **模型**：先报把握（1–5），然后用你自己的话说明：两类页各自和 finalize 的关系是什么，以及为什么 finalize 之前不能运行 TVM。

> **你**：把握 4。measured 只能在 finalize 前加，zero 没限制。finalize 前状态不完整，跑起来行为不可预期。

> **模型**：对的部分：measured 只能在 finalize 前加，准确。一处你很确定但材料说法不同：zero pages 不是无限制，而是只能在 finalize 之后加（`sbi_cove.adoc` §5.3）。追问一个：为什么"zero 不计入测量"恰好推出"它只能在之后加"？

> **你**：因为不计入测量，加了不改变身份，所以冻结后加也没关系；反过来 measured 会改身份，必须在冻结前。

> **模型**：这就到位了——finalize 是测量提交点，两类页落在它两侧。判定：掌握，回答到了本质层。记录中……下一节。

### 5.4 验收辅助概念、细化一节

> **你**：验收 TVM 退出路径。

> **模型**：TVM 因 trap 或中断退出时，控制权怎样交到 host 手里、host 能看到什么、看不到什么？（作答后）正确，且指出了"看不到"的部分。记为验收通过，不影响本节进度。

> **你**：先细化 NACL 共享内存。

> **模型**：已生成 `zoom/s02-guide.md`：NACL 解决的问题、机制、两个例子、边界。读完回来答本节主问题——细化是准备，不代替检验。

### 5.5 概念笔记

在任何文档里写 `[[证书链]]`，或把它写进 `concepts/_inbox.md`，然后：

> **你**：/whetstone:clarify

> **模型**：扫描到 2 个未解决的链接：证书链（units/s04.md）、DICE（outline.md）。为每个生成 `concepts/<名>.md`：解决什么问题、机制、两个例子、边界与误解、相关概念的链接、回链到所在的节。材料里没有依据的部分标为外部知识并附来源。inbox 已清空。

### 5.6 继续课程

> **你**：继续我的课程，课程目录 …/whetstone/courses/cove-attestation/

> **模型**：先做一道检验：**有一种说法是"zero pages 可以在任何时候添加，因为它们不参与测量"。这个说法哪里有问题？**

> **你**：前半句错。不参与测量是对的，但正因如此它只能在 finalize 之后加，之前加会……其实之前加也不改测量？

> **模型**：你抓住了矛盾点——"不改测量"是真的，所以规范的限制不是为了保护测量，而是为了让 finalize 之前的内存布局完全由 measured pages 决定、可复现。纠正到此为止。上次进度：第 3 节已完成，第 4 节待学。**第 4 节 · 当前问题**——

这条"说法"来自你自己上次的回答，但系统不会告诉你，也不会引用原文。

### 5.7 快速模式与结课

快速模式下核心概念照常进主问题，回答方向对就给一句修正、直接下一节；结课时要求你不看顺序把各节的问题 → 方案串起来，标准是"能串起来、说出关键取舍的方向"。快速模式的证据在知识库里单独标记，下门课再遇到这些概念会先出变式题，不会直接跳过。

完整模式的结课总结：

> **模型**：**已解释成功（即时证据，非长期）**：第 1、2、4 节的因果链。**提示后成功（下次继续时值得变式复测）**：第 3 节的"逐层派生 vs 固定密钥"。**仍待复习**：证书 label 的用途。**材料不确定处**：`attestation.adoc` 中 sealing 2.0 标为 TBD。本课程略过：第 5 节（你已有经验）。

## 6. 材料太杂：先规划

典型场景：一个工作目录里有几个上游仓库、自己写的方案、AI 会话生成的总结与交接、几 GB 的日志。直接把整个目录交给 `learn` 也会走同样的评估，单独跑 `guide` 则只规划不开课。

### 6.1 按材料学

> **你**：/whetstone:guide → 规划。目录 /Users/me/Project/tee，我想学的是里面的可信计算部分

> **模型**：先一轮背景与目标：为什么学、相关经验、学完要能做什么、默认深度、要不要知识库？

> **你**：巩固自己做的 MySQL-in-Occlum + mTLS 工作；Occlum 和 SGX 有半年经验；要能解释为什么这样设计并能排障；完整；开知识库

> **模型**：扫描完成（`survey/materials-survey.md`）：14 个顶层条目，3 GB——4 个上游仓库、`文档/` 12 份（4 份带会话或汇报的痕迹）、顶层 6 份进展汇报与交接、`data/` 2 GB 日志（排除）。目的是巩固自己的工作，所以你的方案是课程材料、上游源码作证据。`文档/2_…需求与评估.md` 和 `…mTLS_精简实施方案.md` 是你写的，还是会话生成的？

> **你**：方案是我写的、核实过；需求评估是会话生成的。

> **模型**：候选 3 门课：1「Capsule Manager 的密钥分发链路」（源码 + 你的精简实施方案，5 节）→ 2「双 enclave mTLS 最小链路」→ 3「Occlum SEFS 子系统」。会话记录、交接、汇报不作来源，只摘"待做事项"做迁移题素材。逐门确认——课程 1：接受、修改还是删掉？

> **你**：接受。后面的都接受。

> **模型**：写入 `learning-plan.md`，三门均已确认。第一门的调用语句：`/whetstone:learn 学习 …，课程目录 whetstone/courses/capsule-manager-keys/`；想先看大纲：`/whetstone:outline whetstone/courses/capsule-manager-keys/`。

材料分四级：一手材料（上游源码、官方文档、规范、教材）、你自己写并核实过的、AI 生成的中间文档（会话总结、交接、汇报）、噪声（日志、构建产物）。AI 生成的中间文档永远不作课程来源，最多用来提示"还有哪些待做事项"。

### 6.2 按领域学：骨架课

如果目标不是"学这批材料"，而是"先把这个领域的基本原理巩固一遍，再决定深入哪块"，在向导第一步说明。区别：

| | 按材料学 | 按领域学 |
|---|---|---|
| 覆盖表 | 按标题逐条，每部分都要有去处 | 按文件：材料池、备用（留给分支）、不用 |
| 第一门课 | 材料的一个子集 | 骨架课：只讲基本原理，规模由原理之间的依赖决定，不设上限 |
| 开课前 | 前置检查 | 每节一道探测题，答对的节由你决定跳不跳 |
| 相关性 | 天然的 | 两张表：每个概念在你材料里的落点（比例只展示、无阈值）；分支候选（原理 → 你的模块 → 实际工作） |
| 之后 | 下一门课 | 结课时从候选里选分支，每个分支变成一门普通课 |

> **你**：/whetstone:guide → 规划。目录 ~/Project/tee；我想从头巩固可信计算，不只是学 Occlum。

> **模型**：记为按领域学。扫描同前。材料池：`occlum/docs`、`occlum/src/libos`；备用：`teeapp/src/ra`、`trustflow-capsule-manager/…`；不用：会话交接、日志。计划：骨架课「可信执行环境的基本原理」+ 4 个分支候选（现在不确认）。骨架课接受？

> **你**：接受。

> **模型**（大纲阶段）：按原理依赖切成 7 节：隔离 → 度量 → 证明 → 密封 → 密钥交付 → LibOS 系统调用 → 侧信道边界。落点 11/14：2 个是外部知识（信任根、证书链），1 个没有落点（Quote 格式）。分支候选 4 条，其中「项目里的远程证明链路」对应你负责的 RA 校验。骨架讲的是通用原理，和教科书重合是正常的；漂不漂你看这两张表判断。模式？没有落点的 Quote 留不留？

> **你**：完整；Quote 留着当通识。

> **模型**：确认，生成 7 份讲义。先做探测：第 1 节——不看材料：为什么只靠操作系统的权限检查不足以保护一段代码的数据？……（7 题后）第 1、2 节探测通过，跳过还是照学？

> **你**：跳过 1，2 照学。

> **模型**：第 1 节记为略过（探测通过）。进入第 2 节……

结课时：

> **模型**：整体重述与迁移题（用你的 `teeapp/src/ra` 出的）完成。分支候选：① 项目里的远程证明链路 ② LibOS 系统调用 ③ Capsule Manager 密钥分发 ④ SEFS。深入哪些、什么顺序？

> **你**：① 然后 ③。

> **模型**：写入 `learning-plan.md` 两门分支课。分支课 ① 的调用语句：`/whetstone:learn 学习 teeapp/src/ra，课程目录 whetstone/courses/ra-chain/`。它回到逐标题的覆盖表；骨架课里记录过的概念，在前置判断时视作已有证据。

## 7. 只改大纲

> **你**：/whetstone:outline whetstone/courses/capsule-manager-keys/ 把第 3 节拆成两节，"证书轮换"升成核心概念

> **模型**：改后：第 3 节拆为「密钥派发」与「证书轮换」，核心概念各 3 个，覆盖表已更新，校验通过。模式仍为完整？

> **你**：确认。

> **模型**：已写回。`units/s03.md` 受影响需要重生成，下次 `learn` 处理。

## 8. 知识库

在档案里写 `knowledge_store=on`，或开课时说一句"开知识库"即开启；不开，一切与单课模式相同。库分两层：工作区里的 `store/`（独立布局是 `whetstone/store/`，统一布局是总目录下的 `store/`；每次作答写这里，不会被请求权限），和你的主目录 `~/.whetstone/`（所有工作区的汇总，结课时推送一次，可能被请求一次权限）。开启后：

- 建课时把课程的参考图导出到 `store/mrg/`，事实与机制一份、后两层另一份；
- 教学时把你每次作答只追加到 `store/lrg/`：原文、模型的读取、与参考图的差异、判定、回答到了哪一层、把握、用时；
- 维护跨课的概念索引 `store/concepts/index.json` 和派生的掌握状态 `store/learner-state.json`：每个概念的证据强弱、有效期、到达过的层、错误说法；
- 新课的前置检查先查你主目录里的汇总索引：学过且仍有效的概念出一道变式题代替检查；过期的先变式题、答错再检查；复习时旧的错误说法以匿名形式回来。
- 结课时 `store_sync.py push` 把这个工作区的索引和掌握状态快照推送到 `~/.whetstone/`，主目录里只有派生状态，没有你的任何原始回答。

首次：

```bash
S=whetstone-ai/plugin/skills/learn/scripts
python3 $S/store_init.py init --store whetstone/store --domain-root 计算机科学
```

统一布局下把 `whetstone/store` 换成总目录下的 `store`。之后模型自己运行登记、导出、追加、重建、推送；换一个工作区再 `init` 一次它自己的 `store/`，推送后主目录里就有两边的汇总；主目录位置由环境变量 `WHETSTONE_HOME` 决定。

| 可以看 | 不要看，规则靠你自己守 |
|---|---|
| `outline.md`、`units/`、`zoom/`、`concepts/` | `learning-progress.json`（你的原始回答） |
| `whetstone/store/mrg/<课程>.json` | `whetstone/store/mrg/*.deep.json`（后两层，看了就变成背诵材料） |
| `whetstone/store/concepts/index.json`、`learner-state.json`、`~/.whetstone/` 整个目录 | `whetstone/store/lrg/*.jsonl`（作答日志） |

看进度：`python3 $S/lrg_record.py show --store whetstone/store --lesson-id <课程>`，只显示计数、判定和层，不显示回答；跨工作区的汇总看 `python3 $S/store_sync.py show`。三节之后可以打分：`python3 whetstone-ai/plugin/evals/score_pack.py whetstone/courses/x --sources-root . --store whetstone/store`，看三个数——来源定位的命中率、每节用时的中位数（模型在提问前后各运行一次 `date +%s`，不是估的）、你的回答到达过哪些层；`--baseline` 可与上次结果逐项比较。

## 9. 学习时的纪律

1. 答题前合上材料。整个方法的依据是"从记忆中重建"，翻着书答就退化成被证明无效的那种。
2. 用自己的话，允许错、允许不完整，不问答案。错误回答是资产，复习题就是从你的错误里来的。
3. 把握打分要诚实。系统优先处理"很确定但错了"；虚报低把握就抹掉了最有价值的信号。
4. 不打开原始回答和后两层的文件。文件在你自己的磁盘上，规则只靠你自己。
5. 前置检查时"不知道"是合法答案。编一个答案只会让课程深度错配；答"不知道"的簇会变成一门前置课，不是惩罚。
6. 一次一节，不赶。追问上限、同节不重复出题都按一节一坐设计。
7. 第一门课用最强的模型。定关系、分层、判断回答到了哪一层都押在模型上；第三方模型也能跑，但第一门课别叠这个变量。

## 10. 出现这些就打断它

协议靠文件结构约束模型，不是万无一失。看到以下任一条，直接说"回到协议"：

| 现象 | 应该是 |
|---|---|
| 没出大纲就开始生成讲义或出题 | 先大纲，停下问你模式 |
| 一次回复把整节的问题、方案、机制、主问题全给了 | 先只给问题让你预测 |
| 文档或对话里出现"实际意义 / 这样设计的理由是 / 本质上" | 这两层不展示 |
| 你答完它直接给完整答案 | 一个针对性追问 |
| 同一节反复问相似问题 | 改更高层级的问题，或留给下次继续时 |
| 一节结束没有记录（问它"这节记录了吗"） | `lrg_record.py append` 或 `learning_state.py record` |
| 校验器报错它却继续 | 修到通过。常见：概念 id 不是 `domain.concept` 形式；覆盖表漏了标题 |
| 引用你以前的回答原文 | 只能以匿名说法出现 |

## 11. 排错

- **`claude plugin install whetstone@whetstone-ai` 报 not found**：本地 marketplace 用旧名注册过。`claude plugin marketplace remove whetstone` 后重新 `add`，或 `install whetstone@whetstone`。
- **Claude Desktop 的 Code 标签页里 `/plugin` 无效**：它不支持这个命令，用终端装或用图形化插件管理器。
- **Claude Desktop 走了第三方 API**：`~/.claude/settings.json` 的 `env` 块（`ANTHROPIC_BASE_URL` 等）Desktop 也会读。挪到 shell 环境变量或项目级 `.claude/settings.json`。
- **`coverage is missing heading '…'`**：材料里有标题没在覆盖表里分配去处。让模型补上，这正是防遗漏的检查。
- **`concepts[i].id must match '<domain>.<concept>'`**：概念 id 要小写 ASCII，如 `cs.tee.enclave`。
- **`refusing to overwrite existing progress file`**：进度已存在，说"继续我的课程"。
- **Claude Desktop 聊天模式找不到脚本**：插件在云端、文件在本地，首条消息里说明脚本目录 `whetstone-ai/plugin/skills/learn/scripts/`。
- **技能列表看不到**：装完要新开会话。

## 12. 命令速查

`$S` = `whetstone-ai/plugin/skills/learn/scripts`（插件安装后为 `${CLAUDE_PLUGIN_ROOT}/skills/learn/scripts`）。

```bash
# 校验课程目录
python3 $S/validate_lesson.py whetstone/courses/x/lesson-plan.json --outline whetstone/courses/x/outline.md \
  --units-dir whetstone/courses/x/units --manifest whetstone/courses/x/sources.json --sources-root .
# 进度
python3 $S/learning_state.py init --lesson-plan whetstone/courses/x/lesson-plan.json --output whetstone/courses/x/learning-progress.json
python3 $S/learning_state.py show --state whetstone/courses/x/learning-progress.json
python3 $S/learning_state.py defer --state whetstone/courses/x/learning-progress.json --section-id s01 --reason "探测通过，学习者选择跳过"
# 记一次作答（知识库）
python3 $S/lrg_record.py append --store store --lesson-id x --section-id s02 --kind checkpoint --response-file /tmp/r.txt \
  --verdict partial --confidence 4 --criteria-met c1,c3 --depth mechanism --extraction /tmp/extraction.json \
  --progress whetstone/courses/x/learning-progress.json --elapsed-seconds 240
# 重建掌握状态（模型通常自动运行）
python3 $S/learner_state_build.py build --store store
# 概念笔记扫描；打包插件
python3 whetstone-ai/plugin/skills/clarify/scripts/scan_wikilinks.py whetstone/courses/x
python3 whetstone-ai/package_plugin.py
```
