# 阶段四：回程

前置课结课（[../protocol/finish.md](../protocol/finish.md) 的整体重述与桥接题做完）之后：

1. 开启知识库时：`index_match.py register`（如未做）、`learner_state_build.py build`，前置课概念进入索引与掌握状态。
2. `learning_state.py unblock --state <父课 learning-progress.json> --section-id <blocked_at>`。
3. 更新 `learning-plan.md` 前置栈：本课标"已完成 <日期>"。
4. 报告一句："回到 `<父课>` 第 `<blocked_at>` 节。"栈里还有更上层时，回到的是直接父课。

父课 resume 时（[../protocol/resume.md](../protocol/resume.md)）：

- 开启知识库：`index_match.py prerequisites --store <工作区>/store --lesson-id <父课> --prerequisite-plan …`，前置课里学过的概念返回 `action: variant`、`via_prerequisite_course` 为本课 id——对被卡簇各出一道变式题，作答记 `--kind variant`（延迟证据），`prerequisite_state.py record` 记 verdict；答错的簇不再建课，按 [../protocol/feedback.md](../protocol/feedback.md) 给一个针对性追问后继续。
- 未开知识库：对被卡簇各出一道靠近父课材料的桥接题，`prerequisite_state.py bridge` 记 `ready | retry | skipped`。
- 然后从 `blocked_at` 那节的 READY 继续。就绪的前置在正课里压缩为一句提醒；仍脆弱的关系嵌入相关节重复检查。

学习者中途放弃前置课时：`unblock` 父课并在栈里标"未完成"，父课照常继续；不清零任何记录。
