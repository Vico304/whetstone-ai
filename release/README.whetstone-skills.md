# Whetstone skills {{version}}

四个技能目录：`learn`（总入口：从规划到教学到复习）、`guide`（规划向导）、`outline`（单独改大纲）、`clarify`（按节的概念解释）。`guide` 与 `outline` 读 `learn/references/stages/` 里的阶段规则，所以四个目录要**并列**放进宿主的技能目录：

- Claude Code 个人技能：`~/.claude/skills/`
- DeepSeek Harness：`~/.agents/skills/`（全局）或 `<项目>/.agents/skills/`
- pi：`~/.pi/agent/skills/`

放好后重开会话，输入 `/` 应看到四个技能。只想装一个入口的宿主用 `whetstone-learn.zip`。文档与源码：https://github.com/Vico304/whetstone-ai 。Apache License 2.0，见 `LICENSE`。
