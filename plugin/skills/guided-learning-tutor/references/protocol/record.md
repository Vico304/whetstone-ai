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
