# PREDICT：预测后再揭示

1. 收到预测后，本节 core 概念带 `cases` 时先把两个案例并列（`lesson_section.py` 打出的案例 1、案例 2），请学习者写出它们的共同结构，再呈现 `solution` 与 `mechanism`，用一两句对照学习者预测与材料实际方案的异同；预测与共同结构只为激活思考，不判分、不记录 verdict；有 `contrast` 的概念，揭示后一句点出最易混的近邻与差在哪个变量；
2. `lesson_section.py` 打出「跨课关系」时，在揭示 `solution` 与 `mechanism` **之前**先问这条关系——"你在之前的课里学过 X，它和本节的 Y 是什么关系？"，一次一条，先答再揭示；对照该关系的 `type` 与 `rationale` 判，答对就一句确认，答错或答偏按 [feedback.md](feedback.md) 给一次追问，然后照常揭示，不阻断本节。开启知识库时记 `lrg_record.py append --kind transfer --concept <他课概念 id> --verdict … --depth …`，不加 `--progress`：这条只落在那个他课概念上，不改变本节 verdict。同一条关系只问一次；
3. 结构讲解节（`kind: "structure"`）：先只给本节的部件名单，请学习者说"谁装在谁里面、谁和谁相连"，再揭示 `diagram.py --section` 的部件图，一两句对照；过程讲解节（`kind: "process"`）：先只给参与者，请学习者排出步骤顺序，再揭示步骤表。两者都不判分、不记录，与其他预测一样只为激活已有知识；学习者说不上来就直接揭示，不追问；
4. `tradeoffs` 与 `new_problem` 留作主问题和追问的素材，不必预先展示。

揭示后进入 MAIN。
