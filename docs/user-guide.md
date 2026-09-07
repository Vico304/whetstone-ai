# Whetstone 使用手册

> 面向使用者的操作手册（v0.4.0，schema 1.2）。设计与理念见 [design.md](design.md)、[learning-layers.md](learning-layers.md)；规范见 [consensus.md](consensus.md)。本手册只讲"怎么用"，示例对话为示意，措辞以实际会话为准。

目录

1. [它是什么、不是什么](#1-它是什么不是什么)
2. [安装](#2-安装)
3. [目录约定](#3-目录约定)
4. [一门课的完整流程](#4-一门课的完整流程)
5. [每个环节的示例](#5-每个环节的示例)
6. [知识库模式](#6-知识库模式)
7. [三个技能的分工](#7-三个技能的分工)
8. [学习者纪律](#8-学习者纪律)
9. [盯守模型：出现这些就打断它](#9-盯守模型出现这些就打断它)
10. [评测与数据](#10-评测与数据)
11. [排错](#11-排错)
12. [命令速查](#12-命令速查)

---

## 1. 它是什么、不是什么

Whetstone 把你给它的材料（教材章节、规范、代码库、论文）重组成一条"问题 → 方案 → 新问题"的路线，然后**逼你逐节自己重建**：先预测，再读方案，合上材料用自己的话解释，自评信心，被追问，再答。它记录你每一次作答（包括错的），跨课累积你对每个概念的掌握与时效。

它**不是**：摘要器、闪卡生成器、问答机器人。它不会把"本质"讲给你听——设计理由和设计思想这两层永远不展示，只用来出题和判断你的回答到了哪一层。

适合：想真正掌握一份技术材料而不是"看过"的人。不适合：想快速浏览、只要结论的人（快速模式也要重建，只是范围小、容错宽）。

## 2. 安装

同一份 `plugin/` 目录适配三个宿主。

### Claude Code（终端 CLI）

```bash
# 方式 1：仅当次会话加载（开发时方便）
claude --plugin-dir /path/to/whetstone-ai/plugin

# 方式 2：注册本地 marketplace 并安装（持久）
claude plugin marketplace add /path/to/whetstone-ai
claude plugin install whetstone@whetstone-ai
claude plugin list
```

新开会话，输入 `/`，应看到 `whetstone:guide`、`whetstone:outline`、`whetstone:learn`、`whetstone:clarify`。

### Claude Desktop

- **Code 标签页**：不支持 `/plugin` 斜杠命令。用上面方式 2 在终端装好即可（共用 `~/.claude/` 配置），或用它的图形化插件管理器上传 `.zip`（把 `.plugin` 改后缀）。
- **聊天（Cowork）模式**：插件上传处选 `dist/whetstone.plugin`。打包命令：仓库根目录 `python3 package_plugin.py`。Cowork 中插件同步到云端容器，而你的材料、课程目录、知识库在本地连接文件夹里——开课时把本地路径说清楚。

### 不走插件机制

把三个技能目录拷到 Claude Code 的个人技能目录，调用名去掉前缀：

```bash
cp -r plugin/skills/guide plugin/skills/outline plugin/skills/learn plugin/skills/clarify ~/.claude/skills/
# 调用：/guide  /outline  /learn  /clarify
```

### Codex / DeepSeek Harness

Codex 通过 `.codex-plugin/plugin.json` 作为插件安装，调用 `$guide / $outline / $learn / $clarify`。

DeepSeek Harness（dsh）按技能目录安装：仓库根目录执行 `./install_skills.sh ~/.agents/skills`（全局）或 `./install_skills.sh <project>/.agents/skills`（项目级，需有 `.git`）。dsh 只识别技能根下的一级子目录，四个技能必须平铺在同一根下（guide / outline 会引用同级的 learn 目录）。重启 dsh 后在 `/` 命令面板的 Skills 组里能看到，调用 `/guide / /outline / /learn / /clarify`。启动方式：`npx @deepseek-ai/dsh web`（浏览器打开 http://127.0.0.1:3080，Node 需 ≥ 22.19 或 ≥ 24），首次在 Settings → Models 填 DeepSeek API key，并用 Choose workspace 选中你的工作目录。

### 检查

```bash
cd plugin && python3 -m unittest discover -s tests   # 应全部通过
```

## 3. 目录约定

建议把材料、课程、知识库放在同一个工作区（Cowork 模式下就是连接的文件夹）：

```text
Learning System/
├── whetstone-ai/            # 本仓库
├── materials/               # 你要学的材料（md / adoc / txt / 代码目录）
├── courses/
│   └── tee-basics/          # 每门课一个目录（学习包）
│       ├── outline.md       # 路线图 + 全部概念 + 覆盖账本 ← 你会读的
│       ├── units/s01.md …   # 每个 unit 的正文 ← 你会读的
│       ├── lesson-plan.json # 机器计划（含隐藏的评估标准）
│       ├── sources.json
│       ├── learning-progress.json   # 进度（不要打开）
│       ├── zoom/            # 按需细化文档
│       └── concepts/        # clarify 生成的概念笔记（Obsidian 双链）
└── store/                   # 知识库（可选，跨课持久；不要打开 lrg/ 与 *.deep.json）
```

用 Obsidian 打开 `courses/` 或整个工作区，`[[概念]]` 双链和关系图直接可用。

## 4. 一门课的完整流程

```text
/whetstone:learn 材料 + 目标 [+ 知识库目录]     （总入口：缺什么补什么）
        ↓
⓪ 无 learner-profile.md → 一轮问目标与背景 → 写档案（跨课）        ← 也可单独 /whetstone:guide
   材料是目录 / 太大 → 扫描定级 → 切成学习计划，逐门确认              ← 也可单独 /whetstone:guide
        ↓
① 本课大纲：问题链 + 全部概念（core/supporting/listed）+ 覆盖账本   ← 也可单独 /whetstone:outline
        ↓  ★ 停下：你确认模式（完整 / 快速）与取舍
② 逐份生成 units/<id>.md（每个 unit 一次独立生成，全部生成完再开课）
        ↓
③ 前置诊断（一次一题；开启知识库时，已学过的概念改出一道变式题）
        ↓
④ 逐 unit 教学：预测 → 揭示方案与机制 → [可细化] → 自评信心 → 作答 → 追问 → 记录
        ↓
⑤ 结课：不看顺序重述整条问题链 + 迁移题；总结分"已解释成功 / 提示后成功 / 待复习 / 材料不确定"
        ↓
中断后：新会话说"继续我的课程" → 先一道变式题或一条匿名错误主张 → 回到未完成 unit
```

### 4.1 选材料

第一门课用**一章教材或一个模块**，30 KB 以内，能切 4–6 个 unit。整本书或整份规范会得到一份很长的大纲，先从中挑一段。代码库先给入口和主流程所在的目录。

### 4.2 开课

熟手（档案已有、材料是单个小文件）一句话就直接到大纲；新手最多三轮：目标与背景一轮、（材料是目录时）计划逐门确认、大纲确认。

```text
/whetstone:learn 学习 /Users/me/Learning System/materials/cove-ch4-attestation.adoc，
知识库目录 /Users/me/Learning System/store，
课程目录 /Users/me/Learning System/courses/cove-attestation/。
我希望学完后能解释远程证明为什么需要信任链，并能判断一个新方案的信任根在哪。
```

不给知识库目录就是单课模式，行为与不开启时完全一致。

### 4.3 大纲确认

模型会停下来，给你 `outline.md` 的路径和摘要，只问一件事：模式，以及想略过 / 加深的 unit。回答示例：

- `完整，就这样`
- `快速，略过 4 和 6`
- `完整；把 listed 里的"DICE 层级"升成 core；第 3 节我熟，略过`
- `你定`（= 完整、不略过）

确认之后它才生成 unit 文档。这是你唯一需要"规划"的时刻。

### 4.4 逐 unit 学习

每个 unit 固定五步，一次只推进一步，模型不会一口气给完：

1. **预测**：只给你"当前问题"，问你会怎么解决——说个方向即可，不判分；
2. **揭示**：给方案与机制（来自 `units/<id>.md`），对照你的预测评一句；此时它会问要不要先**细化**本节（候选来自本节 listed 概念）；
3. **信心 + 作答**：先报 1–5 的信心，再用自己的话回答主问题；
4. **追问**：针对你回答里最弱的一点问一个问题（边界 / 反例 / 因果 / 删除 / 对比），最多两层；
5. **记录**，进入下一节。

想验收某个 supporting 概念，任何时候说"验收 X"。

### 4.5 中断与继续

```text
继续我的课程，课程目录 /Users/me/Learning System/courses/cove-attestation/，知识库 /Users/me/Learning System/store
```

它先出一道**变式题**（换情境考已完成节的同一机制），或从你过去的错误主张里取一条以匿名形式让你批判，然后回到未完成的 unit。

## 5. 每个环节的示例

以下对话为示意，材料设为一份 RISC-V 保密计算规范的"远程证明"章节。

### 5.1 大纲确认

> **模型**：大纲已生成：`courses/cove-attestation/outline.md`。
> 推断的目标：解释远程证明为什么需要信任链，并能判断新方案的信任根在哪。共 5 个 unit：
> 1. 为什么 host 说的话不能信 → 用硬件根信任签名的测量
> 2. 测量什么、何时冻结 → measured pages 与 finalize
> 3. 谁来签、密钥从哪来 → 逐层派生（DICE）而非固定密钥
> 4. 依赖方怎么验 → 证书链与 evidence 格式
> 5. 哪些攻击不在范围内 → 威胁模型边界
>
> 概念共 19 个：core 9、supporting 6（含"TVM 退出路径""zero pages"）、listed 4（各 SBI 函数名、CDDL 字段）。账本：`attestation.adoc` 全部标题已分配；`appendix_b.adoc` 的错误码表标为不讲（与目标无关）。
>
> 两个决定请你定：① 完整还是快速？② 想略过或加深的 unit、想升成 core 的概念？

> **你**：完整。第 5 节我做过威胁建模，略过；"TVM 退出路径"升成 core。

> **模型**：已写回：模式 full；unit 5 标为略过（理由：学习者已有经验）；"TVM 退出路径"改为 unit 2 的 core。正在生成 4 份 unit 文档……全部通过校验。开始前置诊断：一次一题。第一题——

### 5.2 前置诊断（知识库命中时）

> **模型**：注册表里有你上门课学过的"G-stage 页表"（延迟证据，12 天前，仍有效）。不重新诊断，出一道变式题代替：**如果 host 能改 G-stage 页表，TVM 的哪一条保证最先失效？** 答完直接进正课。

> **你**：内存隔离。host 把 TVM 的页映射到自己的地址空间就能读。

> **模型**：对。记为 ready，跳过该项诊断。下一项"测量"没有记录，正常诊断——

### 5.3 一个 unit 的完整回合

> **模型**：**Unit 2 · 当前问题**：依赖方要验证 TVM 的初始状态，但 TVM 是由不可信的 host 一页一页搭起来的。你觉得该测量什么、在什么时候停止测量？（说个方向，不判分）

> **你**：测量所有加载的页，创建完成时停。

> **模型**：方向对，"什么时候停"正是规范设计的关键。方案与机制见 `units/s02.md`：页分两类——measured pages 拷贝并计入测量，zero pages 清零不计入；`finalize` 是测量提交点。本节内部还有 `[[NACL 共享内存]]`、`[[promote_to_tvm]]` 等 listed 概念，想先细化哪一个，还是直接回答本节问题？

> **你**：直接答。

> **模型**：先报信心（1–5），然后用你自己的话说明：两类页各自和 finalize 的关系是什么，以及**为什么** finalize 之前不能运行 TVM。

> **你**：信心 4。measured 只能在 finalize 前加，zero 没限制。finalize 前状态不完整，跑起来行为不可预期。

> **模型**：对的部分：measured 只能在 finalize 前加——准确。一处你很确定但材料说法不同：zero pages **不是**无限制，而是只能在 finalize **之后**加（`sbi_cove.adoc` §5.3）。追问一个：为什么"zero 不计入测量"恰好推出"它只能在之后加"？

> **你**：因为不计入测量，加了不改变身份，所以冻结后加也没关系；反过来 measured 会改身份，必须在冻结前。

> **模型**：这就到位了——finalize 是测量提交点，两类页落在它两侧。verdict：mastered，到达层 rationale。记录中……下一节。

### 5.4 验收一个 supporting 概念

> **你**：验收 TVM 退出路径。

> **模型**：TVM 因 trap 或中断退出时，控制权怎样交到 host 手里、host 能看到什么、看不到什么？

> **你**：TSM 把原因写进 scause，把允许 host 看的寄存器放进共享内存，其余寄存器由 TSM 保存，host 看不到。

> **模型**：正确，且指出了"看不到"的部分。记为 supporting 验收通过，不影响本节进度。

### 5.5 细化（DEEPEN）

> **你**：先细化 NACL 共享内存。

> **模型**：已生成 `zoom/s02-guide.md`：NACL 解决的问题、机制、两个例子（一个本规范语境、一个换成 x86 的对照）、边界。读完回来答本节主问题——细化是准备，不替代检验。

### 5.6 概念笔记（clarify）

在任何文档里写 `[[证书链]]`，或把它写进 `concepts/_inbox.md`，然后：

> **你**：/whetstone:clarify

> **模型**：扫描到 2 个未解决链接：证书链（units/s04.md）、DICE（outline.md）。为每个生成 `concepts/<名>.md`：解决什么问题、机制、两个例子、边界与误解、相关概念双链、回链到 unit。材料中没有依据的部分标 `external` 并附来源。inbox 已清空。

### 5.7 继续课程（resume）

> **你**：继续我的课程，课程目录 …/courses/cove-attestation/，知识库 …/store

> **模型**：先做一道检验：**有一种说法是"zero pages 可以在任何时候添加，因为它们不参与测量"。这个说法哪里有问题？**

> **你**：前半句错。不参与测量是对的，但正因如此它只能在 finalize 之后加，之前加会……其实之前加也不改测量？

> **模型**：你抓住了矛盾点——"不改测量"是真的，所以规范的限制不是为了保护测量，而是为了让 finalize 之前的内存布局完全由 measured pages 决定、可复现。纠正到此为止。上次进度：unit 3 已完成，unit 4 待学。**Unit 4 · 当前问题**——

（这条"说法"来自你自己上次的回答，但系统不会告诉你，也不会引用原文。）

### 5.8 快速模式

> **你**：快速，略过 4。

> **模型**：模式 fast：只保留 unit 1–3 与 5，core 概念照常进检查点，回答方向对就给修正继续，结课时请你整体重述。……
>
> （unit 2 作答后）你说的两类页关系方向对了，细节上 zero pages 只能在 finalize 之后加。继续 unit 3。

结课时它会要求你不看顺序把 5 个 unit 的问题 → 方案串起来，验收标准是"能串起来、说出关键取舍的方向"。快速模式的证据在知识库里按 fast 记录，下门课再遇到这些概念会先出变式题而不是直接跳过。

### 5.9 结课总结（节选）

> **模型**：**已解释成功（即时证据，非长期）**：unit 1、2、4 的因果链。**提示后成功（resume 时值得变式复测）**：unit 3 的"逐层派生 vs 固定密钥"。**仍待复习**：证书 label 的用途。**材料不确定处**：`attestation.adoc` 中 sealing 2.0 标为 TBD。本课程略过：unit 5（学习者已有经验）。

## 6. 知识库模式

指定一个持久化目录即开启；不指定则一切与单课模式相同。

### 6.1 它做什么

- build 时把课程导出为**分层参考图**：`store/mrg/<课程>.json`（公开层：事实与机制）和 `<课程>.deep.json`（高层：设计理由与思想，只用于出题与评估）；
- 教学时把你每次作答**只追加**到 `store/lrg/<课程>.jsonl`（原文、模型抽取、去主体化命题、差异清单、到达层、信心、用时）；
- 跨课**概念注册表** `store/concepts/index.json`；派生的**学习者状态** `store/learner-state.json`（每个概念的证据等级、稳定性、fresh/stale/unknown、到达层、错误命题池）；
- 新课前置阶段查注册表：学过且仍有效的概念**出一道变式题替代诊断**；过期的先变式题、答错再诊断。

### 6.2 首次

```bash
S=whetstone-ai/plugin/skills/learn/scripts
python3 $S/store_init.py init --store store --domain-root 计算机科学
```

之后每门课在开课语句里给出 `store` 的绝对路径即可，模型会自己跑 register / export / append / build。

### 6.3 你可以看的、不该看的

| 可以看 | 不该看（规则靠你自己守） |
|---|---|
| `outline.md`、`units/*.md`、`zoom/`、`concepts/` | `learning-progress.json`（你的原始回答） |
| `store/mrg/<课程>.json`（公开层） | `store/mrg/*.deep.json`（高层——看了就变成背诵材料） |
| `store/concepts/index.json`、`store/learner-state.json`（状态与时效） | `store/lrg/*.jsonl`（作答日志） |

想知道进度：`python3 $S/lrg_record.py show --store store --lesson-id <课程>`——只显示计数、判定和到达层，不显示回答。

### 6.4 手动命令（模型通常自动执行）

```bash
S=whetstone-ai/plugin/skills/learn/scripts
python3 $S/store_init.py register --store store --lesson-plan courses/x/lesson-plan.json
python3 $S/mrg_export.py courses/x/lesson-plan.json --store store --manifest courses/x/sources.json
python3 $S/index_match.py register --store store --lesson-id x
python3 $S/index_match.py prerequisites --store store --prerequisite-plan courses/x/prerequisite-plan.json
python3 $S/learner_state_build.py build --store store
python3 $S/learner_state_build.py show --store store
python3 $S/review_pool.py --store store --lesson-id x --progress courses/x/learning-progress.json
python3 $S/store_init.py show --store store
```

## 7. 四个技能的分工

| 技能 | 何时用 | 产出 |
|---|---|---|
| `guide` | 每次都先问"怎么用 / 规划"。第一次用；或想（重新）定目标与背景；或手里是一个混杂目录、不确定该学哪部分 | `learner-profile.md`（跨课的背景与目标）、`materials-survey.md/json`、`learning-plan.md`（课程序列，逐门确认，每门带调用语句） |
| `outline` | 想看、改或重做某门课的大纲 | `courses/<id>/outline.md` + `lesson-plan.json`（确认后写回） |
| `learn` | 总入口：开课、教学、继续。缺档案 / 计划 / 大纲时自动补，等价于依次跑 guide → outline 再 build | 学习包（outline、units、lesson-plan、进度）；开启知识库时写 store |
| `clarify` | 遇到不懂的概念，写了 `[[概念]]` 之后 | `concepts/<概念>.md`，Obsidian 双链 |

三个规划文件的寿命不同：档案跨课（慢变），计划跨几门课，大纲只属于一门课。改哪个就调哪个技能；`learn` 读全部。阶段协议只在 `learn/references/stages/` 维护一份，`guide` 与 `outline` 是入口。

### 7.1 材料太杂时：先跑向导

典型场景：一个工作目录里有几个上游仓库、自己写的方案、AI 会话生成的总结与交接、几 GB 的日志。直接把整个目录喂给 `learn` 也会走同样的评估，但单独跑 `guide` 可以只做规划不开课。

> **你**：/whetstone:guide

> **模型**：想先知道**怎么用**，还是现在就**规划之后的学习**？

> **你**：规划。目录 /Users/me/Project/tee，我想学的是里面的可信计算部分

> **模型**：先一轮背景与目标（写进 `learner-profile.md`）：为什么学、相关经验、学完要能做什么、默认深度和要不要知识库？

> **你**：巩固自己做的 MySQL-in-Occlum + mTLS 工作；Occlum 和 SGX 有半年经验；要能解释为什么这样设计并能排障；完整；知识库 /Users/me/Learning System/store

> **模型**：扫描完成（`materials-survey.md`）：14 个顶层条目，3 GB——4 个上游仓库（`occlum` 416 MB，有 docs；`trustflow-teeapps`；`trustflow-capsule-manager` 513 KB；`teeapp-sgx-rwa-release` 是发布树，与 `trustflow-teeapps-rwa` 重叠）；`文档/` 12 份，4 份带会话/汇报信号；顶层 6 份进展汇报与交接；`data/` 2 GB 日志：排除。
> 目的是巩固自己的工作，所以你的方案是课程材料、上游源码作证据；`文档/2_…需求与评估.md` 和 `…mTLS_精简实施方案.md` 是你写的还是会话生成的？

> **你**：方案是我写的、核实过；需求评估是会话生成的。

> **模型**：候选 3 门课，先看全貌：1「Capsule Manager 的密钥分发链路」（`trustflow-capsule-manager/capsule-manager/src/` + 你的精简实施方案，≈ 2400 行 + 9 KB，5 个 unit）→ 2「双 enclave mTLS 最小链路」（`trustflow-teeapps/teeapps/mysql_server_launcher/` + 分阶段规划）→ 3「Occlum SEFS 子系统」（`occlum/src/libos/crates/sefs*`）。会话记录、交接、汇报不作来源，只摘"待做事项"做迁移题素材；发布树排除。
> 逐门确认——**课程 1**：接受 / 修改 / 删掉？

> **你**：接受。后面的都接受。

> **模型**：写入 `learning-plan.md`，三门均已确认，第一门是课程 1。调用语句：`/whetstone:learn 学习 …，课程目录 courses/capsule-manager-keys/`。想先看大纲：`/whetstone:outline courses/capsule-manager-keys/`。

向导到此结束，不开课。

### 7.2 只改大纲

> **你**：/whetstone:outline courses/capsule-manager-keys/ 把第 3 节拆成两节，"证书轮换"升成 core

> **模型**：改后大纲：第 3 节拆为「密钥派发」与「证书轮换」，core 概念各 3 个，账本已更新，校验通过。确认模式仍为完整？

> **你**：确认。

> **模型**：已写回，`outline_confirmed_at` 更新。`units/s03.md` 受影响需要重生成——下次 `learn` 会处理。

## 8. 学习者纪律

按重要程度：

1. **答题前合上材料。** 整个方法的证据基础是"从记忆中重建"；翻着书答，活动就退化成被证伪的那种。
2. **用自己的话，允许错、允许不完整，不问答案。** 错误回答是资产——去主体化的复习题就是从你的错误里来的。
3. **信心自评要诚实。** 系统优先处理"高信心但错"；虚报低信心就抹掉了最有价值的信号。
4. **不打开日志和高层文件**（§6.3）。文件在你自己的磁盘上，规则只靠你自己。
5. **前置诊断时"不知道"是合法答案。** 编一个答案只会让课程深度错配。
6. **一次一个 unit，不赶。** 追问上限、同节不重复出题都按一节一坐设计。
7. **模型用最强的，走官方账号。** 定关系、标层、判到达层都押在强模型上；协议在第三方 DeepSeek 上也能跑，但第一门课别叠这个变量。

## 9. 盯守模型：出现这些就打断它

协议靠文件结构约束模型，但不是万无一失。看到以下任一条，直接说"回到协议"：

| 现象 | 应该是 |
|---|---|
| 没出大纲就开始生成 units 或出题 | 先大纲，停下问你模式 |
| 一次回复把整节的问题、方案、机制、主问题全给了 | 先只给问题让你预测 |
| 文档或对话里出现"实际意义 / 这样设计的理由是 / 本质上" | 这两层永不展示 |
| 你答完它直接给完整答案 | 一个针对性追问 |
| 同一节反复问相似问题 | 改更高层级的问题，或留给 resume |
| 一节结束没有记录（问它"这节记录了吗"） | `lrg_record.py append` 或 `learning_state.py record` |
| 校验器报错它却继续 | 修到通过（常见：概念 id 不是 ASCII 的 `domain.concept`；账本漏标题） |
| 引用你以前的回答原文 | 只能以匿名命题出现 |

## 10. 评测与数据

三节之后：

```bash
python3 whetstone-ai/plugin/evals/score_pack.py courses/x --sources-root . --store store
```

看三个数：`locator_hit_rate`（引文定位是否真的能在材料里找到）、`median_checkpoint_elapsed_s`（每节交互时间——结构化记录的成本，阈值 +30%）、`depths`（你的回答到达了哪些层）。`--baseline` 可与上次结果逐项比较。每节的用时由模型在提问前后各跑一次 `date +%s` 计算，不是估的。

## 11. 排错

**`claude plugin install whetstone@whetstone-ai` 报 not found in marketplace** —— 本地 marketplace 是用旧名注册的。`claude plugin marketplace remove whetstone` 后重新 `add`，或直接 `install whetstone@whetstone`。

**Desktop 的 Code 标签页里 `/plugin` 无效** —— 它不支持该命令，用终端装或图形化插件管理器。

**Desktop 走了我的第三方 API** —— 第三方配置写在 `~/.claude/settings.json` 的 `env` 块（`ANTHROPIC_BASE_URL` 等）时 Desktop 也会读。挪到 shell 环境变量或项目级 `.claude/settings.json`，Desktop 就回到官方账号。

**校验器：`coverage is missing heading '…'`** —— 材料里有标题没在账本里分配去处。让模型补上（core / supporting / listed / deferred / excluded 带理由），这正是防遗漏的检查。

**校验器：`concepts[i].id must match '<domain>.<concept>'`** —— 概念 id 要小写 ASCII，如 `cs.tee.enclave`；模型写了中文 id。

**`refusing to overwrite existing progress file`** —— 进度已存在，用 resume 而不是重新 init。

**Cowork 模式脚本找不到** —— 插件在云端，文件在本地：首条消息里说明脚本目录 `whetstone-ai/plugin/skills/learn/scripts/` 和各路径。

**技能列表看不到 `whetstone:*`** —— 装完要新开会话。

## 12. 命令速查

```bash
# 校验学习包（1.2）
python3 $S/validate_lesson.py courses/x/lesson-plan.json --outline courses/x/outline.md \
  --units-dir courses/x/units --manifest courses/x/sources.json --sources-root .
# 校验旧包（1.0/1.1）
python3 $S/validate_lesson.py courses/old/lesson-plan.json --guide courses/old/teaching-guide.md
# 进度
python3 $S/learning_state.py init --lesson-plan courses/x/lesson-plan.json --output courses/x/learning-progress.json
python3 $S/learning_state.py show --state courses/x/learning-progress.json
# 记一次作答（知识库模式）
python3 $S/lrg_record.py append --store store --lesson-id x --section-id s02 --kind checkpoint \
  --response-file /tmp/r.txt --feedback-file /tmp/f.txt --verdict partial --confidence 4 \
  --criteria-met c1,c3 --depth mechanism --extraction /tmp/extraction.json \
  --progress courses/x/learning-progress.json --elapsed-seconds 240
# 概念笔记扫描
python3 whetstone-ai/plugin/skills/clarify/scripts/scan_wikilinks.py courses/x
# 打包插件
python3 whetstone-ai/package_plugin.py
```

`$S` = `whetstone-ai/plugin/skills/learn/scripts`（插件安装后为 `${CLAUDE_PLUGIN_ROOT}/skills/learn/scripts`）。
