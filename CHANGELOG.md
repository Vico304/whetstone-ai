# 更新记录

## 未发布

- 证据等级按间隔判定，不再按题型：与教学同场的作答（`checkpoint / probe / diagnostic`）一律即时；其余题型要与该概念的上一条记录隔一夜（更早的本地日期且至少 8 小时）才算延迟，迁移题在此基础上算迁移。事件里不再写 `evidence_tier`，重建掌握状态时按概念重算（`build --tz` 指定时区）。每节用时 `elapsed_seconds` 改由脚本按与上一条记录的间隔算（超过 3 小时记空，`elapsed_source` 标来源），协议不再要求模型运行 `date +%s`。`lrg_record.py append` 与 `learning_state.py record` 加 `--at`（回填，另记 `recorded_at`）与 `--force`；同一节、同题型、回答原文相同的记录默认拒绝。起因：真实数据里 31 个"有效期内"的概念全是同日证据，43 条记录没有一条有用时。
- `AGENTS.md`（`CLAUDE.md` 指向它）给在仓库里工作的 AI 会话定规则：用语按 `docs/glossary.md`、一个概念一个名字、长度上限、只改被要求改的协议、提交前检查。`check_docs.py` 把断链、手册里的设计用语、旧词、长度上限做成检查，CI 每次运行。
- 前置课（schema 1.4）：前置检查、骨架课探测轮或大纲确认时发现的缺口，一律建成一门普通课（`prerequisite_of`、`blocked_at`、`depth`），来源用外部存档、模式跟随父课、大纲照常确认、逐节教学与记录；父课在被卡的节 `block`，前置课结课后 `unblock` 并对被卡簇出变式题；前置课里学过的概念不看时效直接出变式题；可递归，学习计划里的前置栈随时可见；自述基础薄弱时探测轮不跳过；校验器打印前置课的 fact 比例，不设阈值。不再生成 `prerequisite-guide.md`；诊断作答可记为 `kind: diagnostic`。
- 外部存档：建前置课、补没有落点的概念、材料只说"是什么"没说"为什么"的机制时，模型可以检索可靠的外部来源，但必须先存进 `<工作区>/external/<集名>_<日期>/`（每集一份 `_index.md`）再引用，不引活 URL，不用外部来源改写原材料的主张。任何课程都可以把外部存档集整目录作 `pool` 进覆盖表；校验器打印外部引用比例，不设阈值。
- 两种布局：独立布局（`<材料根>/whetstone/`）之外，支持统一布局——一个总目录管所有材料和课程（`material/`、`courses/<目标>/`、`store/`）。工作区按打开的目录判断；计划目录可按学习目标分组；`sources.json` 的 `base_path` 改为记录材料根相对课程目录的位置，校验器与评分器据此自动找到来源，课程目录搬到哪种布局都能校验；`source_manifest.py --rebase` 迁移旧清单。
- 知识库改为本地优先：库固定在工作区里的 `store/`，每次作答只写工作区内，不再每节请求写入权限；跨工作区的记忆放到 `~/.whetstone/`（`WHETSTONE_HOME` 可改），由结课时 `store_sync.py push` 把本工作区的索引与掌握状态快照汇总过去，主目录里没有原始回答。`index_match.py` / `review_pool.py` 加 `--home` 读汇总；档案的 `knowledge_store` 改为 on/off。起因：库在工作区之外时每一节都要申请一次写权限。
- 适配 pi：根目录 `package.json` 的 `pi.skills` 指向 `plugin/skills`，`pi install git:github.com/Vico304/whetstone-ai` 或本地路径即可安装；`install_skills.sh` 也可装到 `~/.pi/agent/skills`。SKILL.md 的路径约定加入 pi 的 `<location>`；调用 `/skill:learn` 等。

## 1.0.0 — 2026-09-09

第一个正式版。功能与 0.6.0 相同，这一版的工作是文档：

- 文档按读者分成两套用语：README 与使用手册只用平实的中文，设计文档与 specs 保留 MRG、LRG、SEL 和 schema 里的字段值；对照表在 `docs/glossary.md`。
- `docs/` 重组为 `design.md`（设计）、`guide.md`（手册）、`evidence.md`（依据与开放问题）、`specs/`（按主题的四份参考：课程文件、取向与骨架课、知识库、教学协议）。共识文档、四份按时间编号的设计定稿、路线图、旧手册、评审与幻灯片删除；v2 设计中未实现的部分（多 Agent 管线、对象模型、质疑通道、可视化导出）不再出现在文档里。
- 示例课程目录的来源冻结为它当初依据的 v1 共识文本（`plugin/examples/project-consensus/source/`），两份评测材料冻结进 `plugin/evals/materials/`，测试、CI 与评测不再依赖 `docs/`。
- 插件内模型读取的文件（`plugin/skills/`）一字未改。

状态：规划管线与建课在 Claude Desktop 和 DeepSeek Harness 上各跑过多次，逐节教学在日常使用中；知识库是可选功能，尚无长期使用数据。

## 0.6.0 — 2026-09-08

- 取向 `material / domain` 与骨架课（schema 1.3）：按文件的材料池、每个概念的落点、每节一道探测题、分支候选表；不设量化上限。起因是一个多仓库加十几份生成文档的目录"太多太杂"，而学习者真正想要的是先巩固领域原理再选方向。
- 两次真实建课（Claude Desktop 聊天模式、DeepSeek Harness）暴露的问题进校验器：URL 当本地路径、supporting 无验收题、`outline_confirmed_at` 午夜占位、探测题混进 unit 文档；定位约定改为"标题原文或符号名开头"（Claude 的定位命中率 0.145，DeepSeek 0.647）。
- 系统写出的一切集中到材料根目录下的 `whetstone/`；技能描述改为中文；unit 文档不再带"验收 X"提醒。

## 0.5.0 — 2026-09-07

- 规划管线分层：`learn` 总入口缺什么补什么，`guide`（档案、材料评估、逐门确认的计划）与 `outline`（单课大纲）是可重入的阶段入口，阶段协议只在 `learn/references/stages/` 维护一份；`survey_materials.py` 清点混杂目录。
- 使用手册；`install_skills.sh` 适配 DeepSeek Harness 与 `~/.claude/skills`。

## 0.4.0 — 2026-09-07

- 大纲先行、必经确认；每节一份独立生成的 `units/<id>.md` 取代单文档讲义；模式 `full / fast`；概念角色 `core / supporting / listed / deferred`，supporting 各带验收题；覆盖表对照材料真实标题检查（schema 1.2）。起因是第一位外部使用者用 CoVE 规范学 7 节后的反馈："核心概念抓得准，但关键细节没涉及"——根因是规划而不是抽取。

## 0.3.0 — 2026-09-05

- 代码评审修复与 CI。
- v2 设计：四层 MRG、高层分文件永不展示；LRG 只追加、对学习者不可见；旧错误以匿名命题复习；受信领域内 MRG 是尺子、比较单向。
- 知识库落地：schema 1.1（概念 id、层、学科路径、关系）、`mrg_export`、结构化 LRG 与比较器、概念索引与派生的掌握状态、变式题代替诊断、评测集；协议按状态拆文件。
- 项目改名 whetstone，主技能改名 learn。

## 0.2.0 — 2026-09-01

- 首次发布：跨宿主教学技能插件（Claude Code、Claude Desktop、Codex、DeepSeek Harness）与设计框架；逐节教学闭环在日常自用。

## 下一步

- 用知识库跑完一门真实课程，拿到每节用时与 `depth_reached` 的第一批数据。
- 可视化导出（先用 Obsidian 目录与 graph）。
- 对参考图的质疑记录与版本化。
- 同一概念在第二门课出现时的跨课对比题。
- 建课管线阶段化，把检索摘要、别名确认交给廉价模型。
