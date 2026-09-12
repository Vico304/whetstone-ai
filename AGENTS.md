# 给在这个仓库里工作的 AI 会话

每个会话开始先读本文件，再动手。Claude Code 通过 `CLAUDE.md` 指到这里；Codex、pi 直接读本文件。

## 语言

- 写任何文档、提交说明、注释之前先读 `docs/glossary.md`，它是用语标准。手册（`README.zh-CN.md`、`docs/guide.md`）不出现 MRG / LRG / SEL、`core / supporting / listed`、`full / fast`、`material / domain`、`fact / mechanism / rationale / principle` 这些词；设计文档与 `docs/specs/` 用它们，首次出现给一次中文。两边都不用 glossary §2 列的旧词。
- 一个概念一个名字。要引入新概念，先在 `docs/glossary.md` §1 加一行再使用；不给已有的东西起第二个名字（例：统一布局的根叫"总目录"，"知识库"只指 `store/`）。
- 平实、专业：短句；不用口语（"随你""就好""弹权限"）；不用营销语；数字带出处；英文只出现在代码字体里。
- 长度上限：README ≤ 120 行，`guide.md` ≤ 350，`design.md` ≤ 250，每份 spec ≤ 200。超了就删，不改上限。
- 只写代码里存在的行为，用现在时。计划写进 `CHANGELOG.md` 的"下一步"，不写进 design 或 specs。
- 提交信息用英文，conventional 前缀（`docs:`、`feat(...):`、`fix:`），正文说为什么。

## 改动

- `plugin/skills/` 是模型读的协议：只在用户明确要求改功能时改，改动最小；`protocol/` 下每个文件 ≤ 60 行。
- 能用 schema、文件边界或校验器表达的约束不写成提示词；真实运行里出的错进校验器。
- 大改动先给方案再动手；逐步提交，每步让用户审。
- 提交前必须通过：`cd plugin && python3 -m unittest discover -s tests`；CI 里的模板与示例目录校验；`python3 check_docs.py`（断链、用语、长度）。
- git 身份 `wangxibin11 <wangxibin11@jd.com>`（用 `-c` 传）；提交尾注 `Co-Authored-By` 与 `Claude-Session`。不 push，不建 release，不请求计算机控制去做这两件事——用户自己做。
