# 各宿主的技能目录与脚本路径

`SKILL.md` 及 references 中出现的 `scripts/`、`assets/`、`references/` 均相对于 **`SKILL.md` 所在目录**（下称技能目录）解析。执行脚本前先确定技能目录的绝对路径：

- Claude Code（插件安装）：技能目录为 `${CLAUDE_PLUGIN_ROOT}/skills/learn`，例如 `python3 "${CLAUDE_PLUGIN_ROOT}/skills/learn/scripts/validate_lesson.py" ...`；
- Claude Code 以个人/项目技能安装（`~/.claude/skills/learn/` 或 `<project>/.claude/skills/learn/`，Claude Desktop 的 Code 标签页也用这条）：技能目录为 `${CLAUDE_SKILL_DIR}`，例如 `python3 "${CLAUDE_SKILL_DIR}/scripts/validate_lesson.py" ...`；
- DeepSeek Harness / 直接放入 `~/.agents/skills/` 或 `.agents/skills/` 的环境：技能目录即被安装的 skill 目录本身；
- pi（`pi install` 装为包，或放入 `~/.pi/agent/skills/`、`.pi/skills/`）：系统提示里 `<location>` 给出 `SKILL.md` 的绝对路径，技能目录就是它所在的目录，脚本用该绝对路径执行；调用 `/skill:learn`；
- Codex：按宿主提供的技能路径解析；
- Claude Desktop 聊天（Cowork）模式：插件在云端容器、材料与课程在本地连接文件夹，脚本必须在本地运行——把本技能的 `scripts/` 复制到学习工作区 `whetstone/scripts/` 后从那里执行（一次即可，重装插件后重新复制）。

shell 的当前工作目录通常是用户项目目录而非技能目录，不要以相对路径直接执行脚本。

