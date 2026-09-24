# Evals

任何提示词、协议切分或管线改动，都要能在同一组材料上看到指标变化；看不到就不改（`docs/specs/protocol.md` §5）。这里不追求绝对值，追求**改动前后可比**。

## 材料

`materials.json` 列出三份来自本仓库的小材料（教材式文档、小代码库、评审式长文），各带学习目标与结构期望（节数范围、每节概念上限、最少关系数）。用被测技能把每份材料 build 成课程目录，放到 `results/<run-id>/<material-id>/`。

## 打分

```bash
# build 指标（结构、支持类型、层分布、引文定位命中率、泄漏检查）
python3 evals/score_pack.py results/<run>/doc-learning-layers \
  --sources-root .. --material-id doc-learning-layers \
  --output results/<run>/doc-learning-layers.json

# 加上 teach 指标（需要用知识库模式教过这个课程目录）
python3 evals/score_pack.py results/<run>/doc-learning-layers \
  --sources-root .. --store <知识库目录> \
  --baseline results/<prev>/doc-learning-layers.json
```

`--baseline` 逐项打印数值差异。

一条命令给 `evals/` 与 `examples/` 下全部课程目录（含 `lesson-plan.json` 的目录）打分，一目录一行：

```bash
python3 evals/score_all.py                      # 默认根目录：evals/ 与 examples/
python3 evals/score_all.py skills/learn/assets --output-dir /tmp/scores
python3 evals/score_all.py --baseline-dir /tmp/scores --output-dir /tmp/scores   # 与上次比较后覆盖
```

状态三种：`ok`（无校验错误，期望满足）、`fail`（有校验错误或 `materials.json` 的期望未满足，目录名等于材料 id 时才核对期望）、`skipped`（不能打分，备注写原因：没有 `lesson-plan.json`、JSON 坏了等）。全部 `ok` 退出 0，有 `fail` 或 `skipped` 退出 1，根目录不存在或一个课程目录都没找到退出 2。`--output-dir` 每个目录写一份与 `score_pack.py --output` 同格式的结果，可作下次的 `--baseline`；`--sources-root`、`--store` 与 `score_pack.py` 同义。

`--baseline-dir` 在表后逐目录与上次 `--output-dir` 写出的同名文件比较，差异按 `score_pack.py --baseline` 的格式列出，末行汇总 `no change / changed / no baseline / bad` 各几个。没有同名文件记 `no baseline`，不算失败；文件读不了、不是 JSON 或根不是对象时在 stderr 打 `ERROR: bad baseline …`，退出 1；目录本身不存在退出 2。数值有差异不影响退出码。先读完比较用的文件再写结果，所以两个选项可以指向同一目录。还没建成课程目录的材料列在表后。`results/example-baseline.json` 是对 `examples/project-consensus` 的一次打分，作为输出格式样例；来源是冻结在 `examples/project-consensus/source/` 里的 v1 共识文本，所以定位可以被脚本核对。

## 前置检查样例

`prerequisites/` 放着 `examples/project-consensus` 的一份前置计划与一份前置作答记录，让前置检查的两个脚本也在同一份材料上可复核：

```bash
python3 skills/learn/scripts/validate_prerequisites.py evals/prerequisites/prerequisite-plan.json \
  --manifest examples/project-consensus/sources.json
python3 skills/learn/scripts/prerequisite_state.py show --state evals/prerequisites/prerequisite-progress.json
```

作答记录由 `prerequisite_state.py` 按计划逐条写出（一簇 `ready`；一簇 `gap` 后回程复测 `ready`），测试会按事件顺序重放并比对。

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
