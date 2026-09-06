# resume 开场：变式检索

进入 `resume` 时，先不进入未完成小节。开场从**已完成的小节**中选一个概念，出一道变式问题：换情境或换角度，但考察同一深层机制；禁止复用原 checkpoint 措辞。学习者作答并获得简短反馈后，再用一两句话重建上下文（"当前主线走到哪、上次遗留什么问题"），然后进入未完成小节的 READY。

变式题的作答通过 `record --review` 追加到对应已完成小节，verdict 照常判定；`mastered` 的小节因变式失败可回到 `in_progress`，这是正常的遗忘信号，不是倒退。`--review` 告诉脚本这是复习而非当前进度：`current_section_id` 不会因此跳回早期小节，学习者仍从上次停下的位置继续；退回 `in_progress` 的小节会在后续小节全部完成后再被安排重做。不加 `--review` 记录变式题会把当前位置错误地拉回该早期小节。

命令见 [record.md](record.md)。

## 开启知识库时：去主体化的错误复习

开场变式题之外（或代替之），可以从学习者过去的错误主张里取一条做复习：

```bash
python3 scripts/learner_state_build.py build --store <知识库目录>
python3 scripts/review_pool.py --store <知识库目录> --lesson-id <lesson-id> --progress path/to/learning-progress.json
```

`review_pool.py` 只读派生状态，返回的每条 `claim` 是抽取时已去主体化的命题（不含"你说""我认为"，不引用原句）。呈现方式固定为匿名主张：

> "有一种说法是「{claim}」。这个说法哪里有问题？"

三条规则：**不说这是学习者自己说过的**；**不展示、不引用任何原始回答**；**纠正在同一轮内给出**——学习者答完立即给出正确说法与证据定位，不能让学习者看完旧的错误主张就离开（错误再暴露只有紧跟纠正时才有正面效果）。作答用 `lrg_record.py append --kind review` 记录到该命题所属的小节；答对后该命题仍留在池中，由时效自然淘汰。

