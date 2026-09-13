# 知识库（可选）

学习者说要知识库（调用语句里的"开知识库"，或 `learner-profile.md` 的 `knowledge_store=on`）时开启；未开启时完全不涉及以下步骤。

**两层，本地优先。** 本工作区的库固定在工作区里的 `store/`（与 `courses/` 同级；独立布局即 `whetstone/store/`，下文命令里的 `<工作区>/store` 照此代入）——建课、每次作答、重建状态都只写这里，宿主已经信任这个目录，不会请求权限。跨工作区的记忆放在学习者主目录 `~/.whetstone/`（可用 `WHETSTONE_HOME` 改），它是各工作区快照汇总出来的派生物，不含任何原始回答；只在两个时刻碰它：开课前**读**一次（`--home`），结课时**推**一次（`store_sync.py push`）。学习者给了别的路径就用那个路径当本地库，但不要再要求把库放到工作区之外。

- 首次：`python3 scripts/store_init.py init --store <工作区>/store [--domain-root 学科名]`；每门课 build 时 `store_init.py register --lesson-plan`；
- build 抽概念时：把候选概念（名称 + 别名）写成 JSON 列表，运行 `scripts/index_match.py recall --home --candidates`（主目录还不存在时改 `--store <工作区>/store`），对每个命中项判断"同一概念 / 同名异义 / 粒度不同"：同一则复用已有 id，不同则新建 id；模型无法确定的（`decision_needed = disambiguate`，或语义上拿不准）向学习者问一句，一次最多 3 个；**禁止按名称相似自动合并**；
- build 校验通过后：`scripts/mrg_export.py <lesson-plan> --store <工作区>/store`，得到公开层 `mrg/<id>.json` 与高层 `mrg/<id>.deep.json`；随后 `scripts/index_match.py register --store <工作区>/store --lesson-id <id>` 把节点登记进本地注册表（脚本报告的 alias 冲突不自动处理，交学习者确认）；
- 每次教学会话结束或 resume 开始时：`scripts/learner_state_build.py build --store <工作区>/store` 重建本地 `learner-state.json`（派生物，不手改）；结课时再 `scripts/store_sync.py push --store <工作区>/store` 把本工作区的快照推进主目录（这是唯一一次写工作区之外，宿主可能问一次权限；学习者拒绝也不影响本课，下次再推）；
- 教学中每次产生 verdict：按 [references/protocol/assess.md](protocol/assess.md) 写抽取 JSON，用 `scripts/lrg_record.py append --store <工作区>/store --progress <learning-progress.json>` 一次完成比较、追加日志、同步进度；
- **三条硬约束**：只从公开层文件渲染任何面向学习者的内容，高层文件只在评估与出题时读取；`lrg/` 下的日志不向学习者展示、不引用原文；学习者对抽取或判定有异议时追加新一次作答，不修改任何已有记录。

详见 `docs/specs/knowledge-store.md`。

