# Evals

任何提示词、协议切分或管线改动，都要能在同一组材料上看到指标变化；看不到就不改（`docs/specs/protocol-architecture.md` §6）。这里不追求绝对值，追求**改动前后可比**。

## 材料

`materials.json` 列出三份来自本仓库的小材料（教材式文档、小代码库、评审式长文），各带学习目标与结构期望（小节数范围、每节概念上限、最少关系数）。用被测技能把每份材料 build 成学习包，放到 `results/<run-id>/<material-id>/`。

## 打分

```bash
# build 指标（结构、支持类型、层分布、引文定位命中率、泄漏检查）
python3 evals/score_pack.py results/<run>/doc-learning-layers \
  --sources-root .. --material-id doc-learning-layers \
  --output results/<run>/doc-learning-layers.json

# 加上 teach 指标（需要用知识库模式教过这份包）
python3 evals/score_pack.py results/<run>/doc-learning-layers \
  --sources-root .. --store <知识库目录> \
  --baseline results/<prev>/doc-learning-layers.json
```

`--baseline` 逐项打印数值差异。`results/example-baseline.json` 是对 `examples/project-consensus` 的一次打分，作为输出格式样例；它的 `locator_hit_rate` 低于 1 是真实信号——该示例课程建于 consensus v1，部分标题定位在 v2 里已不存在。

## 指标含义

| 指标 | 关注什么 |
|---|---|
| `validator_errors / warnings` | 结构契约是否被遵守；warnings 含认知负担与 rationale 层泄漏提示 |
| `sections`、`max_concepts_per_section` | 课程规模是否落在期望区间（新概念 ≤ 4） |
| `support`、`unsupported_ratio`、`pedagogical_inference_ratio` | 证据质量；教学推断占比过高说明抽取在编关系 |
| `relations`、`layers` | 1.1 的图是否真的被填了；层标注分布是否合理（全是 mechanism 说明没标） |
| `locator_hit_rate` | 引文定位是否真的能在来源文件里找到——最便宜的"MRG 抽取忠实度"代理 |
| `median_checkpoint_elapsed_s` | **交互成本**。结构化记录前后对比，阈值 +30% |
| `depths`、`conflicts_per_attempt`、`high_confidence_conflict_share` | 教学是否把学习者推到了更高层；高信心冲突是否被识别 |

## 尚未自动化

teach 侧的"一次回复只推进一个状态""首次重建前不出现 criteria 文本""追问是否引用了回答内容"需要对话回放，目前靠人工抽查；`depth_reached` 与人工判定的一致率也是人工。宿主提供 eval 框架（如 skill-creator）时优先接入。
