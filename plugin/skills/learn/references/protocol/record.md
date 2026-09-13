# 进度记录

文件模式使用（技能目录的绝对路径按 [../hosts.md](../hosts.md) 取）：

```bash
python3 scripts/learning_state.py init \
  --lesson-plan path/to/lesson-plan.json \
  --output path/to/learning-progress.json

python3 scripts/learning_state.py record \
  --state path/to/learning-progress.json \
  --section-id s01 \
  --response-file path/to/raw-response.txt \
  --feedback-file path/to/feedback.txt \
  --verdict partial \
  --confidence 4 \
  --criteria-met c1,c3 \
  --depth mechanism
```

`--criteria-met` 填回答满足的 `checkpoint.criteria[].id`（1.0 课程用 `c1`、`c2`… 按顺序编号）；`--depth` 填 [assess.md](assess.md) 判定的到达层。两者都可省略，但省略等于丢掉已经做完的诊断。

resume 开场的变式检索题记录时加 `--review`（见 [resume.md](resume.md)），其余主问题和追问作答不加：

```bash
python3 scripts/learning_state.py record \
  --state path/to/learning-progress.json \
  --section-id s01 \
  --response-file path/to/variant-response.txt \
  --verdict retry \
  --review
```

`record` 会追加尝试并原子更新状态；它不会删除早期回答。每条尝试带 `kind`（`checkpoint` 或 `review`）记题型；证据是即时还是延迟，在重建掌握状态时按间隔判定，不由题型决定。同一节里回答原文相同的记录会被拒绝（多半是重复写入），确认要记再加 `--force`；回填过去的作答用 `--at <带时区的时间>`。学习者标注了信心就传 `--confidence`，未标注则省略。保存原始回答和后续修订；不得用修订覆盖首次回答。若不适合把回答写入文件，则只在当前对话保留，并明确无法跨 session 恢复。

## 开启知识库时

用 `lrg_record.py append` 代替 `learning_state.py record`：它运行比较器、把事件追加到本工作区 `whetstone/store/lrg/<lesson-id>.jsonl`（只写工作区内，不弹权限），并通过 `--progress` 同步 `learning-progress.json`（同样遵守 `--review` 语义，用 `--kind review`）：

```bash
python3 scripts/lrg_record.py append \
  --store whetstone/store --lesson-id <lesson-id> --section-id s01 \
  --kind checkpoint \
  --response-file path/to/raw-response.txt --feedback-file path/to/feedback.txt \
  --verdict partial --confidence 4 --criteria-met c1,c3 --depth mechanism \
  --extraction path/to/extraction.json \
  --progress path/to/learning-progress.json
```

`--kind`：`checkpoint`（主问题与追问）/ `supporting`（supporting 概念的验收，需 `--concept <id>`，不加 `--progress`）/ `review`（resume 变式）/ `variant`（跨课前置替代题）/ `transfer`（迁移题、接缝题）/ `bridge`（前置桥接复测）/ `final`（课程结束整体重述）。每节用时由脚本按与本课上一条记录的间隔自动算（超过 3 小时记空），不要自己估；只有确实计了时才传 `--elapsed-seconds`。`--at` 与 `--force` 同 `learning_state.py record`。`--rigor full|fast` 默认取进度文件的 `mode`。日志只增不改；`lrg_record.py show` 只显示计数与层次，不显示回答。

