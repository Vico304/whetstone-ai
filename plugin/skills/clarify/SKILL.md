---
name: clarify
description: Maintain an Obsidian-compatible concept-note directory for a guided-learning lesson pack. Scan inbox lists and unresolved [[wikilinks]] left by the learner, then write one source-grounded, example-rich note per unclear concept, cross-linked with the teaching guide and other notes. Use when the learner has marked concepts they do not understand and asks to expand them.
---

# Clarify：概念笔记维护

学习者在学习包的任何文档里用 `[[概念名]]` 标记不理解的概念，或把概念列进 `concepts/_inbox.md`，然后调用本技能。技能为每个未解决的概念生成一份有来源、多例子的概念笔记，并用 Obsidian 双链把笔记、教学文档和其他概念互相连接。

调用方式：Codex 中 `$clarify`；Claude Code 中 `/guided-learning-tutor:clarify` 或自然语言触发；DeepSeek Harness 中 `/clarify`。

## 路径解析约定

本文档中 `scripts/`、`assets/` 相对于本 SKILL.md 所在目录（技能目录）解析：

- Claude Code（插件安装）：技能目录为 `${CLAUDE_PLUGIN_ROOT}/skills/clarify`；
- Claude Code 以个人/项目技能安装（`~/.claude/skills/clarify/`）：技能目录为 `${CLAUDE_SKILL_DIR}`；
- DeepSeek Harness / 直接放入 `~/.agents/skills/` 的环境：技能目录即被安装的 skill 目录本身。

shell 的 cwd 通常是用户项目目录，不要以相对路径直接执行脚本。概念笔记写入学习包的 `concepts/` 目录，与技能目录无关。

## 输入来源

按优先级合并三类输入，去重后逐个处理：

1. 用户在调用时直接给出的概念名；
2. `concepts/_inbox.md` 中的条目（每行一个，允许 `- 概念` 列表格式或裸文本）；
3. 学习包内所有 `.md` 文件中**未解决的 wikilink**（`[[目标]]` 没有对应笔记文件）。

用脚本做确定性扫描，不要凭印象判断哪些链接未解决：

```bash
python3 <技能目录>/scripts/scan_wikilinks.py <学习包目录> --inbox <学习包目录>/concepts/_inbox.md
```

脚本按文件名和 frontmatter `aliases`（行内 `[a, b]` 或 YAML 块列表均可）匹配已有笔记，输出缺失目标及其出现位置。围栏代码块与行内代码中的 `[[...]]` 会被跳过；HTML 注释等其他嵌入形式仍可能误报，处理前人工确认。

## 工作流

1. 定位学习包目录（含 `lesson-plan.json` 或 `teaching-guide.md` 的目录）；没有学习包时也可以在用户指定的任意笔记目录内工作，但来源约束仍然生效。
2. 运行扫描脚本，汇总待处理概念，向用户报告清单；数量多时按教学主线相关性排序，一次处理不超过 5 个，其余留在 inbox。
3. 对每个概念：
   - 先在学习包的来源材料（`sources.json` 所列文件、`lesson-plan.json` 的 `source_refs`）中检索该概念的出现位置；
   - 材料内有依据的内容按实际支持类型标注（`explicit / entailed`）；材料未覆盖的部分需要外部检索时，遵循与前置补充相同的规则：可审核来源、标记 `external`、记录出处，检索不可用时明确说明而不伪造；
   - 按 [assets/concept-note-template.md](assets/concept-note-template.md) 写入 `concepts/<概念名>.md`，文件名即 wikilink 目标；
   - 已有笔记时增量补充，不覆盖已有内容中学习者手写的部分。
4. 处理完毕后从 `_inbox.md` 移除已完成条目（inbox 是队列，不是记录），并报告：新建/更新了哪些笔记、哪些概念在材料中找不到依据、哪些留待下次。

## 概念笔记契约

每份笔记必须包含（模板已体现）：

- **先试提示**置顶：一句"先自己解释一遍再往下读"的检索提示——概念笔记是参考材料，但阅读前的一次检索尝试成本极低、收益明确；
- 它解决什么问题（为什么存在，而不只是是什么）；
- 机制（如何工作）;
- **至少两个例子**，其中至少一个贴近学习包的材料语境；
- 边界与常见误解；
- 与其他概念的关系：用 `[[概念]]` 链接，并写明关系类型和理由，不用裸链接堆砌；
- 出现位置：链接回教学文档相关小节（`[[teaching-guide#小节标题]]`）；
- 来源：path、locator、support 类型。

frontmatter 使用 `aliases`（中英文变体、缩写）和 `status`（`draft | grounded | external-supplemented`）。

## 边界

- **不得泄漏检查点**：若概念是某个尚未作答小节的核心概念，笔记照常生成（阅读是学习的一部分），但不得逐字给出该小节 `checkpoint.criteria` 的答案，且先试提示改为更明确的"建议先完成该节重建再阅读本条"；
- 默认**不改写 teaching-guide**：笔记单向链接回教学文档即可；用户明确要求时才在教学文档的概念首次出现处加 `[[链接]]`，且不得改变原文含义；
- 不把概念笔记当摘要器出口：一次批量生成整个材料所有概念的笔记不是本技能的用途，笔记只为学习者实际标记的疑问服务；
- Obsidian 互链依赖文件名匹配：建议用户把学习包目录放进 vault（或作为 vault 打开）；概念改名时同步更新引用。
