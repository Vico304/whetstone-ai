# Guided Learning Tutor

一个跨宿主的学习技能插件。它读取用户明确提供的文档、代码库或会话记录，把材料改写成"问题 → 方案 → 新问题"的教学文档，然后逐节要求学习者解释并给予证据约束的反馈。

同一份技能目录同时适配三个宿主：

| 宿主 | 安装方式 | 调用方式（brief / 主技能 / clarify） |
|---|---|---|
| **Codex** | 通过 `.codex-plugin/plugin.json` 作为插件安装 | `$brief` / `$guided-learning-tutor` / `$clarify` |
| **Claude Code** | 通过 `.claude-plugin/plugin.json` 作为插件安装 | `/guided-learning-tutor:brief`、`/guided-learning-tutor:guided-learning-tutor`、`/guided-learning-tutor:clarify`，或自然语言自动触发 |
| **DeepSeek Harness (dsh)** | 把 `skills/` 下各技能目录复制到 `~/.agents/skills/`（全局）或项目的 `.agents/skills/` | `/brief` / `/guided-learning-tutor` / `/clarify` |

三个宿主共享同一份 `SKILL.md` 契约（YAML frontmatter + 渐进加载的 references/scripts），无需为各宿主维护分支。

插件包含三个技能：

- **brief**：课前简报。生成正式教学包之前，通过少量提问澄清学习者背景、学习目标、材料性质与约束，轻量扫描材料后生成一份《学习任务简报》（含粗粒度阶段规划和可复制的调用话术），学习者自行细化修改；后续每次调用主技能时随材料一并提供，避免重复解释背景；
- **guided-learning-tutor**：主技能。材料 → 问题链课程 → 逐节主动重建教学；提供了简报时自动将其作为任务背景读取；
- **clarify**：概念笔记维护。学习者在任何文档里用 `[[概念名]]` 标记不理解的概念，或写进 `concepts/_inbox.md`，调用后自动生成有来源、多例子的概念笔记，与教学文档 Obsidian 双链互通。

## 为什么是这个版本

Whetstone 框架（见仓库 [`docs/design.md`](../docs/design.md) 与 [`docs/consensus.md`](../docs/consensus.md) v2）包含来源证据层、分层的机器参考图、只追加的学习者重建日志、跨课概念注册表、带时效的学习者状态和多角色审核。当前插件只保留能构成完整学习闭环的最小主链：

```text
（可选）课前简报：澄清背景与目标 → 学习者细化修改
        ↓
材料范围与来源定位
        ↓
总体问题与系统地图
        ↓
前置依赖与学习者准备度
        ↓
针对缺口的有引用补充与桥接复测
        ↓
问题—方案—新问题教学链
        ↓
逐节：预测 → （可选）按需细化本节 → 主动解释（带信心标注）→ 针对性追问
        ↓
证据约束的反馈与修订 · [[概念]] 疑问随时进 concepts 收件箱
        ↓
恢复时变式检索 · 整体重述与迁移问题
```

它暂不实现持久化知识库、自动跨材料合并、多 Agent 发布流程、间隔复习调度或独立 Web UI。这样可以先验证最重要的假设：问题驱动的文档和逐节主动解释，是否真的比摘要更能帮助用户理解材料。

### 知识库模式（v2，可选开启）

设计见 [`docs/specs/`](../docs/specs/)。在调用时指定一个持久化目录（或在简报里填 `knowledge_store`）即开启；不开启时行为与 v0.2 完全一致。开启后：

- **分层机器参考图**：build 校验通过后 `mrg_export.py` 把课程导出为 `mrg/<id>.json`（`fact / mechanism` 公开层）与 `mrg/<id>.deep.json`（`rationale / principle` 高层）。讲义、概念笔记、学习者查询只读公开层；高层只在评估与出题时加载。
- **只追加、不可见的学习者日志**：每次作答由模型读成抽取 JSON（概念、关系、去主体化命题），`comparator.py` 落差异类别（不打分），`lrg_record.py` 追加到 `lrg/<id>.jsonl` 并同步 `learning-progress.json`。`show` 只显示计数与层次，永不打印回答。
- **跨课注册表与带时效的学习者状态**：`index_match.py` 按别名召回已学概念（不自动合并）；`learner_state_build.py` 从日志派生每个概念的证据等级、稳定性、`fresh / stale / unknown` 时效、到达层与错误命题池。
- **变式题替代诊断**：新课前置阶段 `index_match.py prerequisites` 对 `fresh / stale` 的概念给一道变式题而不是完整诊断——不跳过。
- **去主体化复习**：`review_pool.py` 从派生状态取出过去的错误主张，以"有一种说法是……哪里有问题？"呈现，纠正同轮闭环，原回答永不展示。
- **evals**：`evals/score_pack.py` 对任何学习包与日志打分，提示词改动前后可比。

尚未实现：可视化导出（`exports/`，P1）、质疑通道的记录脚本（P1）、build 管线阶段化与廉价模型分工（P1）。

高层内容永不展示、LRG 不可见不可改、第四层理解只记录不评分——这三条是 v2 的硬约束，见 [`docs/learning-layers.md`](../docs/learning-layers.md)。

## 核心能力

- 混合分析 Markdown、纯文本、代码目录和用户提供的会话导出；
- 把来源内容与来源中的指令分开，避免把材料正文当成操作命令；
- 从材料中识别会阻断主线理解的最小前置概念簇；
- 通过无提示、一次一问的方式评估与当前材料相关的学习准备度；
- 针对实际缺口检索权威或一手来源，生成标记为 `external` 的补充文档和桥接复测；
- 生成从大框架到细节的 `teaching-guide.md`；
- 生成可校验的 `lesson-plan.json` 和 `sources.json`；
- 分段揭示教学：先给问题请学习者预测，再展示方案与机制；
- 逐节提问、针对回答实际暴露的弱点追问、诊断高信心误解，并保留多次原始回答；
- 恢复学习时先用变式检索题检验已完成小节的留存；
- 使用标准库 Python 脚本清点来源、校验课程结构和维护学习进度；
- 可选的知识库模式：分层 MRG 导出、结构化 LRG 日志与比较器、跨课概念注册表、带时效的学习者状态、变式题替代诊断、去主体化复习（见下节）。

## 使用示例

安装后不需要每次重复完整提示词，给出材料和目标即可。

Codex：

```text
使用 $guided-learning-tutor 学习这些材料：
- /path/to/document.pdf
- /path/to/repository

我希望学完后能够：解释核心设计，并把它应用到新问题。
```

Claude Code（或直接用自然语言描述学习需求触发）：

```text
/guided-learning-tutor:guided-learning-tutor 学习 /path/to/document.pdf，
我希望学完后能解释核心设计并应用到新问题。
```

DeepSeek Harness：

```text
/guided-learning-tutor 学习 /path/to/document.pdf，
我希望学完后能解释核心设计并应用到新问题。
```

技能会默认补全 `build + teach`、`prerequisite_check=auto`、来源约束、独立课程目录、进度文件和逐节教学节奏。明确知道自己缺少前置知识时，可以加一句"我可能缺少前置知识，请先诊断"。

前置检索依赖宿主提供的网络搜索或浏览能力。宿主策略禁用检索时，插件会明确报告限制，而不伪造来源。

会话记录只有在当前对话可见、用户提供了导出文件/链接，或宿主明确提供了相应读取工具时才能分析。插件不会读取隐藏会话。

## 目录

```text
plugin/
├── .claude-plugin/plugin.json   # Claude Code manifest
├── .codex-plugin/plugin.json    # Codex manifest
├── docs/design.md
├── examples/project-consensus/
│   ├── sources.json
│   ├── lesson-plan.json
│   └── teaching-guide.md
├── tests/test_tools.py
├── evals/                           # 材料清单 + score_pack.py
└── skills/                          # 三宿主共享的技能目录
    ├── brief/                       # 课前简报技能
    │   ├── SKILL.md
    │   └── assets/
    ├── guided-learning-tutor/       # 主技能
    │   ├── SKILL.md
    │   ├── agents/openai.yaml       # 仅 Codex 使用，其他宿主忽略
    │   ├── assets/
    │   ├── references/
    │   │   ├── protocol/            # 教学协议，按状态机状态分文件加载
    │   │   ├── prerequisite/        # 前置协议，按阶段分文件加载
    │   │   ├── lesson-contract.md
    │   │   └── source-handling.md
    │   └── scripts/
    └── clarify/                     # 概念笔记技能
        ├── SKILL.md
        ├── assets/
        └── scripts/
```

## 各宿主安装说明

**Claude Code**（三种方式，任选其一）：

```bash
# 1. 终端 CLI，仅当次会话加载（开发时最方便）
claude --plugin-dir /path/to/whetstone-ai/plugin

# 2. 终端 CLI 注册本地 marketplace 并安装（持久；Claude Desktop 的 Code 标签页共用同一份用户配置）
claude plugin marketplace add /path/to/whetstone-ai
claude plugin install guided-learning-tutor@whetstone

# 3. 不走插件机制：作为个人技能放进 ~/.claude/skills/（调用名变为 /brief、/guided-learning-tutor、/clarify）
cp -r plugin/skills/brief plugin/skills/guided-learning-tutor plugin/skills/clarify ~/.claude/skills/
```

注意：**Claude Desktop 的 Code 标签页不支持 `/plugin` 斜杠命令**（它有图形化插件管理器）；在 Desktop 里用方式 2（先在终端装好）或方式 3。会话内输入 `/` 确认技能出现。

**Claude Desktop / Cowork 上传安装**：两个入口都接受 zip 格式的插件包（`.plugin` 就是改了后缀的 zip，根目录含 `.claude-plugin/plugin.json`）。在仓库根目录执行

```bash
python3 package_plugin.py            # 生成 ../dist/guided-learning-tutor.plugin
```

然后在 Desktop 的插件上传处选择该文件。改过技能后重新打包、重新上传。Cowork 模式下插件被同步到云端容器，而学习包和知识库应放在连接的本地文件夹里——首条消息里说明知识库与课程目录的本地路径即可。

**DeepSeek Harness**：

```bash
cp -r plugin/skills/brief plugin/skills/guided-learning-tutor plugin/skills/clarify ~/.agents/skills/
# 或项目级：复制到 <project>/.agents/skills/
```

**Codex**：通过个人 marketplace 安装本目录。

## 本地验证

在 plugin 目录执行：

```bash
python3 -m unittest discover -s tests -v
python3 skills/guided-learning-tutor/scripts/validate_lesson.py \
  skills/guided-learning-tutor/assets/lesson-plan-template.json \
  --guide skills/guided-learning-tutor/assets/teaching-guide-template.md

python3 skills/guided-learning-tutor/scripts/validate_lesson.py \
  examples/project-consensus/lesson-plan.json \
  --guide examples/project-consensus/teaching-guide.md \
  --manifest examples/project-consensus/sources.json
```

纯标准库 Python，无第三方依赖。安装或更新插件后，请在新会话中测试以加载最新技能指令。
