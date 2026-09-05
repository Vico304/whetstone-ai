# 逐节教学协议：状态机与加载表

协议按状态拆分。**只读当前状态对应的文件**，不要一次加载全部。

```text
READY
  ↓ 只揭示本节"当前问题"，请学习者预测方案
PREDICT
  ↓ 学习者预测后，揭示方案与机制，对照预测简评一句
MAIN ←──────────────────┐
  ↓ 提出主问题前询问是否细化本节        │
  ├─ 学习者选择细化 → DEEPEN（生成细化文档，读完返回）
  ↓ 请学习者先自评信心（1–5）再作答
AWAITING_ATTEMPT
  ↓ 学习者回答
ASSESS
  ├─ MASTERED ───────→ 简短巩固后进入下一节 READY
  ├─ PARTIAL ────────→ 一个针对性追问 → AWAITING_RETRY
  ├─ MISCONCEPTION ──→ 证据纠正 + AWAITING_RETRY
  ├─ SKIPPED ────────→ 下一节 READY
  └─ PAUSED ─────────→ 保存当前位置
```

| 当前状态 | 读取 |
|---|---|
| READY | [ready.md](ready.md) |
| PREDICT | [predict.md](predict.md) |
| DEEPEN | [deepen.md](deepen.md) |
| MAIN / AWAITING_ATTEMPT | [main.md](main.md) |
| ASSESS | [assess.md](assess.md) |
| 反馈与追问（ASSESS 之后、AWAITING_RETRY） | [feedback.md](feedback.md) |
| 进入 `resume` 时 | [resume.md](resume.md) |
| 记录进度（任何产生 verdict 的时刻） | [record.md](record.md) |
| 最后一节完成后 | [finish.md](finish.md) |

一次回复只推进一个状态。提出问题或追问后应把对话交还给学习者，不同时回答自己的问题。

若正课中暴露出之前未识别的前置缺口，只对受影响的概念簇运行 [../prerequisite/](../prerequisite/_index.md) 协议，补充和桥接复测后回到原小节。不因一个缺口将整门课程或学习者状态清零。
