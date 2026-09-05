# 进度记录

文件模式使用（路径按 SKILL.md 的路径解析约定取技能目录绝对路径）：

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

`record` 会追加尝试并原子更新状态；它不会删除早期回答。每条尝试带 `kind`（`checkpoint` 或 `review`），便于日后区分即时证据与延迟证据。学习者标注了信心就传 `--confidence`，未标注则省略。保存原始回答和后续修订；不得用修订覆盖首次回答。若不适合把回答写入文件，则只在当前对话保留，并明确无法跨 session 恢复。

## 开启知识库时

用 `lrg_record.py append` 代替 `learning_state.py record`：它运行比较器、把事件追加到 `<store>/lrg/<lesson-id>.jsonl`，并通过 `--progress` 同步 `learning-progress.json`（同样遵守 `--review` 语义，用 `--kind review`）：

```bash
python3 scripts/lrg_record.py append \
  --store <知识库目录> --lesson-id <lesson-id> --section-id s01 \
  --kind checkpoint \
  --response-file path/to/raw-response.txt --feedback-file path/to/feedback.txt \
  --verdict partial --confidence 4 --criteria-met c1,c3 --depth mechanism \
  --extraction path/to/extraction.json \
  --progress path/to/learning-progress.json \
  --elapsed-seconds 240
```

`--kind`：`checkpoint`（主问题与追问）/ `review`（resume 变式）/ `variant`（跨课前置替代题）/ `transfer`（迁移题、接缝题）/ `bridge`（前置桥接复测）/ `final`（课程结束整体重述）。`--elapsed-seconds` 记本节从提出主问题到判定的墙钟时间——这是判断结构化记录成本是否可承受的唯一指标，尽量填。日志只增不改；`lrg_record.py show` 只显示计数与层次，不显示回答。

