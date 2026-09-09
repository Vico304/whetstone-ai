# 更新记录

## 1.0.0 — 2026-09-09

第一个正式版。功能与 0.6.0 相同，这一版的工作是文档：

- 文档按读者分成两套用语：README 与使用手册只用平实的中文，设计文档与 specs 保留 MRG、LRG、SEL 和 schema 里的字段值；对照表在 `docs/glossary.md`。
- `docs/` 重组为 `design.md`（设计）、`guide.md`（手册）、`evidence.md`（依据与开放问题）、`specs/`（按主题的四份参考：课程文件、取向与骨架课、知识库、教学协议）。共识文档、四份按时间编号的设计定稿、路线图、旧手册、评审与幻灯片删除；v2 设计中未实现的部分（多 Agent 管线、对象模型、质疑通道、可视化导出）不再出现在文档里。
- 示例课程包的来源冻结为它当初依据的 v1 共识文本（`plugin/examples/project-consensus/source/`），两份评测材料冻结进 `plugin/evals/materials/`，测试、CI 与评测不再依赖 `docs/`。
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
