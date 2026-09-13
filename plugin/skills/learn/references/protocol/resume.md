# resume 开场：变式检索

进入 `resume` 时先看进度文件有没有 `blocked`：有 → 这门课在等一门前置课，不在这里继续；报告栈（"本课卡在第 X 节，等 `<子课>`"），转去 resume 那门前置课（它自己若也 blocked，再往下）。前置课刚结课回来的（`unblock` 事件是最近一条）→ 先按 [../prerequisite/return.md](../prerequisite/return.md) 对被卡簇出变式题，再从 `blocked_at` 那节的 READY 继续，本文下面的开场变式题可省。

其它情况：先不进入未完成小节。开场从**已完成的小节**中选一个概念，出一道变式问题：换情境或换角度，但考察同一深层机制；禁止复用原 checkpoint 措辞。学习者作答并获得简短反馈后，再用一两句话重建上下文（"当前主线走到哪、上次遗留什么问题"），然后进入未完成小节的 READY。

变式题的作答通过 `record --review` 追加到对应已完成小节，verdict 照常判定；`mastered` 的小节因变式失败可回到 `in_progress`，这是正常的遗忘信号，不是倒退。`--review` 告诉脚本这是复习而非当前进度：`current_section_id` 不会因此跳回早期小节，学习者仍从上次停下的位置继续；退回 `in_progress` 的小节会在后续小节全部完成后再被安排重做。不加 `--review` 记录变式题会把当前位置错误地拉回该早期小节。

命令见 [record.md](record.md)。

## 开启知识库时：去主体化的错误复习

开场变式题之外（或代替之），先重建掌握状态，再按 `review_pool.py` 输出的 `order` 取题：`suspect`（假性掌握——已掌握但前置薄弱的概念，对它出变式题）→ `items`（错误主张，见下）→ `missing_edges`（链重建漏掉或反向的边，问"X 和 Y 之间是什么关系"）→ `stale`（过期概念）。取错误主张时：

```bash
python3 scripts/learner_state_build.py build --store whetstone/store
python3 scripts/review_pool.py --store whetstone/store --lesson-id <lesson-id> --progress path/to/learning-progress.json
# 想把别的工作区里学过的错误主张也拿来复习：--home 代替 --store（读学习者主目录，一次）
```

`review_pool.py` 只读派生状态，返回的每条 `claim` 是抽取时已去主体化的命题（不含"你说""我认为"，不引用原句）。呈现方式固定为匿名主张：

> "有一种说法是「{claim}」。这个说法哪里有问题？"

三条规则：**不说这是学习者自己说过的**；**不展示、不引用任何原始回答**；**纠正在同一轮内给出**——学习者答完立即给出正确说法与证据定位，不能让学习者看完旧的错误主张就离开（错误再暴露只有紧跟纠正时才有正面效果）。作答用 `lrg_record.py append --kind review` 记录到该命题所属的小节；答对后该命题仍留在池中，由时效自然淘汰。

